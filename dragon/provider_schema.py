"""Provider-free validation of the serialized Codex structured-output schema.

Policy source: https://developers.openai.com/api/docs/guides/structured-outputs
Supported references/unions are inspected, not silently removed. This gate
does not validate evidence or weaken response semantics.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from jsonschema import Draft202012Validator, SchemaError


AUDITED_KEYWORDS = (
    "allOf", "oneOf", "anyOf", "$ref", "$defs", "definitions", "if", "then",
    "else", "not", "dependentRequired", "dependentSchemas",
)
SUPPORTED_KEYWORDS = {
    "$schema", "$defs", "$ref", "type", "properties", "required",
    "additionalProperties", "items", "anyOf", "enum", "const", "description",
    "title", "minLength", "maxLength", "pattern", "format", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minItems", "maxItems",
}
SUPPORTED_TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}
SUPPORTED_FORMATS = {"date-time", "time", "date", "duration", "email", "hostname", "ipv4", "ipv6", "uuid"}


def serialized_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def schema_preflight(schema_text: str, *, model: str = "") -> dict:
    errors: list[dict] = []
    counts = dict.fromkeys(AUDITED_KEYWORDS, 0)
    properties = enums = string_size = maximum_depth = 0
    try:
        schema = json.loads(schema_text)
        Draft202012Validator.check_schema(schema)
    except (ValueError, SchemaError) as exc:
        return {"status": "FAIL", "schema_sha256": text_hash(schema_text),
                "keyword_counts": counts, "errors": [{"path": "$", "reason": str(exc)}]}

    def fail(path: str, reason: str) -> None:
        errors.append({"path": path, "reason": reason})

    def walk(node: object, path: str, depth: int) -> None:
        nonlocal properties, enums, string_size, maximum_depth
        maximum_depth = max(maximum_depth, depth)
        if not isinstance(node, dict):
            fail(path, "Boolean/non-object schemas are outside the provider subset")
            return
        for key in node:
            if key in counts:
                counts[key] += 1
            if key not in SUPPORTED_KEYWORDS:
                fail(path + "/" + key, "Unsupported structured-output keyword")
        kind = node.get("type")
        types = kind if isinstance(kind, list) else [kind] if kind else []
        if any(item not in SUPPORTED_TYPES for item in types):
            fail(path + "/type", "Unsupported type/union")
        if isinstance(kind, list) and (len(kind) != 2 or "null" not in kind):
            fail(path + "/type", "Use one concrete type plus null, or a supported nested anyOf")
        if not types and not any(key in node for key in ("anyOf", "$ref")):
            fail(path, "Schema requires a type, supported anyOf, or local reference")
        if "object" in types:
            fields = node.get("properties", {})
            if node.get("additionalProperties") is not False:
                fail(path, "Objects require additionalProperties=false")
            if set(node.get("required", [])) != set(fields):
                fail(path, "Every object property must be required")
            properties += len(fields)
            string_size += sum(len(key) for key in fields)
            for key, child in fields.items():
                walk(child, path + "/properties/" + key, depth + 1)
        if "array" in types:
            if "items" not in node:
                fail(path, "Array items schema is required")
            else:
                walk(node["items"], path + "/items", depth + 1)
        for index, child in enumerate(node.get("anyOf", [])):
            walk(child, path + f"/anyOf/{index}", depth)
        for key, child in node.get("$defs", {}).items():
            string_size += len(key)
            walk(child, path + "/$defs/" + key, depth)
        if "$ref" in node:
            reference = node["$ref"]
            try:
                if reference == "#":
                    target = schema
                elif isinstance(reference, str) and reference.startswith("#/"):
                    target = schema
                    for part in reference[2:].split("/"):
                        target = target[part.replace("~1", "/").replace("~0", "~")]
                else:
                    raise ValueError("Only document-local references are supported")
                if not isinstance(target, dict):
                    raise ValueError("Reference does not resolve to a schema")
            except (KeyError, TypeError, ValueError) as exc:
                fail(path + "/$ref", str(exc))
        values = node.get("enum", [])
        enums += len(values)
        enum_string_size = sum(len(item) for item in values if isinstance(item, str))
        string_size += enum_string_size
        if len(values) > 250 and enum_string_size > 15000:
            fail(path + "/enum", "Large enum exceeds provider string limit")
        if isinstance(node.get("const"), str):
            string_size += len(node["const"])
        if "format" in node and node["format"] not in SUPPORTED_FORMATS:
            fail(path + "/format", "Unsupported string format")
        if model.startswith("ft:"):
            for key in {"minLength", "maxLength", "pattern", "format", "minimum", "maximum", "multipleOf", "minItems", "maxItems"} & node.keys():
                fail(path + "/" + key, "Constraint unsupported for a fine-tuned model")

    if not isinstance(schema, dict) or schema.get("type") != "object" or "anyOf" in schema:
        fail("$", "Provider root must be an object, without root anyOf")
    walk(schema, "$", 1)
    if properties > 5000 or maximum_depth > 10 or enums > 1000 or string_size > 120000:
        fail("$", "Schema exceeds provider property/depth/enum/string limits")
    return {"status": "FAIL" if errors else "PASS", "schema_sha256": text_hash(schema_text),
            "keyword_counts": counts, "object_properties": properties, "maximum_depth": maximum_depth,
            "enum_values": enums, "schema_string_size": string_size, "errors": errors,
            "policy_source": "https://developers.openai.com/api/docs/guides/structured-outputs"}


def payload_preflight(operation: str, payload_text: str) -> dict:
    errors = []
    try:
        payload = json.loads(payload_text)
        if not isinstance(payload, dict):
            raise ValueError("Provider payload must be an object")
        if operation == "research":
            if payload.get("schema_version") != 5 or payload.get("language") != "ar":
                raise ValueError("Research payload requires V5 and Arabic language")
            date.fromisoformat(payload["edition_date"])
            if not isinstance(payload.get("continuity"), dict) or not isinstance(payload.get("edition_readiness"), dict):
                raise ValueError("Research continuity and edition readiness must be objects")
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {"status": "FAIL" if errors else "PASS", "payload_sha256": text_hash(payload_text), "errors": errors}

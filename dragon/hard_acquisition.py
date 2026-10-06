"""Deterministic acquisition bookkeeping, never an evidence evaluator.

Only one candidate path per mandatory lane is active. Discovery alternatives
remain in the receipt; only an explicit failed inspection permits promotion.
Unknown claim topology conservatively reserves primary and independent work.
"""
from copy import deepcopy
import hashlib
from urllib.parse import urlsplit


LANES = ("ACCOUNTABILITY", "SERVICE")
CAPACITY_BLOCK = "MANDATORY_PROTOCOL_EXCEEDS_REMAINING_CAPACITY"


def candidate_claim_contexts(packet):
    """Preserve original claim scope for the unchanged claim-sensitive policy."""
    return {section['section_id'] + ':' + candidate['id']:
            {k:deepcopy(candidate[k]) for k in ('title','facts','claims','claim_type','story_type') if k in candidate}
            for section in packet.get('sections', [])
            for candidate in section.get('candidates', []) + section.get('recovery_candidates', [])}


def lane(action):
    return action.get("target_editorial_function")


def core(action):
    return bool(action.get("recovery_need_id") and not action.get("lead_followup")
                and not action.get("dynamic_recovery") and not action.get("actor_first_search")
                and not action.get('event_lead_feedback') and not action.get('direct_source_route')
                and float(action.get('strategy_index', 0)).is_integer()
                and not str(action.get('query_variant') or '').endswith('_FALLBACK')
                and action.get("lead_origin") != "PROVIDER_EXACT")


def exact(action):
    return (urlsplit(str(action.get("target") or "")).path.lower().endswith(".pdf")
            or action.get("selected_target_class") == "EXACT_ARTIFACT")


def required_for_path(action, path):
    if path.get('required_roles') != ['PRIMARY']:
        return True
    if action.get('query_intent') == 'LISTING_TO_DETAIL_EXACT_ARTIFACT':
        return True  # an explicitly selected artifact must still be inspected
    return not (action.get('provider_source_role') == 'INDEPENDENT' or action.get('event_lead_feedback')
                or (action.get('provenance_requirements') or {}).get('required_role') == 'INDEPENDENT')


class HardAcquisition:
    def __init__(self, mandatory_lanes, actions=(), receipt=None):
        self.lanes = tuple(mandatory_lanes)
        self.data = deepcopy(receipt or {"protocol": "staged-hard-acquisition-v1",
            "paths": {}, "selected": {}, "completed_action_ids": [], "core_action_ids": [],
            "blocker": None, "minimum_remaining_required_actions": 0, "action_paths": {}, "allowance_blockers": []})
        self.data.setdefault('action_paths', {})
        self.data.setdefault('allowance_blockers', [])
        self.data.setdefault('candidate_claim_contexts', {})
        for action in actions:
            self.register(action)

    def register(self, action):
        if lane(action) not in self.lanes:
            return None
        if core(action):
            if action["action_id"] not in self.data["core_action_ids"]:
                self.data["core_action_ids"].append(action["action_id"])
            return None
        identity = self.data['action_paths'].get(action['action_id']) or action.get("acquisition_path_id") or action.get("provider_candidate_id")
        if not identity:
            value = str(action.get("target") or action.get("originating_observation_id") or action["action_id"])
            identity = lane(action) + ":" + hashlib.sha256(value.encode()).hexdigest()[:16]
        path = self.data["paths"].setdefault(identity, {"path_id": identity, "lane": lane(action),
            "state": "DISCOVERED", "actions": {}, "failure_reasons": [], "rank": [9, identity]})
        item = deepcopy(action)
        item["acquisition_path_id"] = identity
        item["required_protocol"] = False
        if item.get('event_lead_feedback'):
            duplicate = next((a for a in path['actions'].values() if a['action_id'] != item['action_id']
                and a.get('event_lead_feedback') and all(a.get(k) == item.get(k)
                    for k in ('action_type', 'query', 'discovery_channel', 'search_language'))), None)
            if duplicate:
                alternatives = path.setdefault('duplicate_role_queries', {})
                alternatives[item['action_id']] = {'action':item, 'reason':'DUPLICATE_SELECTED_ROLE_QUERY',
                                                   'existing_action_id':duplicate['action_id']}
                return identity
        if (action.get('lead_followup') and not action.get('dynamic_recovery')
                and action.get('provider_source_role') != 'INDEPENDENT'
                and (action.get('provenance_requirements') or {}).get('required_role') != 'INDEPENDENT'):
            # One pending primary navigation frontier per selected candidate.
            # An exact document replaces an unexecuted generic child; retain
            # the displaced route as an alternative, with its original parent.
            pending = [a for a in path['actions'].values() if a.get('lead_followup')
                       and not a.get('dynamic_recovery') and a.get('provider_source_role') != 'INDEPENDENT'
                       and (a.get('provenance_requirements') or {}).get('required_role') != 'INDEPENDENT'
                       and a['action_id'] not in self.data['completed_action_ids'] and a['action_id'] != action['action_id']]
            if pending:
                competing = min(pending + [item], key=lambda a: (not exact(a), a['action_id']))
                displaced = item if competing is not item else pending[0]
                alternative_id = identity + ':ALTERNATE:' + displaced['action_id']
                self.data['action_paths'][displaced['action_id']] = alternative_id
                path['actions'].pop(displaced['action_id'], None)
                displaced = {**displaced, 'acquisition_path_id':alternative_id, 'fallback_parent_path_id':identity}
                self.data['paths'][alternative_id] = {'path_id':alternative_id, 'lane':lane(action),
                    'state':'FALLBACK_IF_CURRENT_PATH_FAILS','actions':{displaced['action_id']:displaced},
                    'failure_reasons':[], 'rank':[3,alternative_id]}
                if competing is not item:
                    return alternative_id
        self.data['action_paths'][action['action_id']] = identity
        path["actions"].setdefault(action["action_id"], item)
        rank = [0 if exact(action) else 1 if action.get("lead_origin") == "PROVIDER_EXACT" else 2, identity]
        path["rank"] = min(path["rank"], rank)
        return identity

    def promote(self):
        for name in self.lanes:
            selected = self.data["selected"].get(name)
            if selected and self.data["paths"][selected]["state"] != "FAILED":
                continue
            candidates = sorted((p for p in self.data["paths"].values()
                                 if p["lane"] == name and p["state"] != "FAILED"), key=lambda p: p["rank"])
            if candidates:
                chosen = candidates[0]
                chosen["state"] = "SELECTED_FOR_QUALIFICATION"
                self.data["selected"][name] = chosen["path_id"]
                for other in candidates[1:]:
                    other["state"] = "FALLBACK_IF_CURRENT_PATH_FAILS"

    def active(self, action):
        if lane(action) not in self.lanes or core(action):
            return True
        identity = self.register(action)
        return (identity == self.data["selected"].get(lane(action))
                and self.data["paths"][identity]["state"] != "FAILED"
                and action['action_id'] in self.data['paths'][identity]['actions']
                and required_for_path(action, self.data['paths'][identity]))

    def actions(self):
        result = []
        done = set(self.data["completed_action_ids"])
        for name in self.lanes:
            identity = self.data["selected"].get(name)
            if not identity or self.data["paths"][identity]["state"] == "FAILED":
                continue
            for a in self.data["paths"][identity]["actions"].values():
                if a["action_id"] not in done and required_for_path(a, self.data['paths'][identity]):
                    result.append({**deepcopy(a), "required_protocol": True,
                                   "acquisition_state": "MANDATORY_FOR_CURRENT_CLOSURE_PATH"})
        return sorted(result, key=lambda a: (not exact(a), a.get("provider_source_role") == "INDEPENDENT", a["action_id"]))

    def minimum(self):
        done = set(self.data["completed_action_ids"])
        count = len(set(self.data["core_action_ids"]) - done)
        for name, identity in self.data["selected"].items():
            path = self.data["paths"][identity]
            if path["state"] == "FAILED":
                continue
            actions = [a for a in path['actions'].values() if required_for_path(a, path)]
            count += sum(a["action_id"] not in done for a in actions)
            # Reservation is acquisition work, not role acceptance. A native
            # primary lead has no independent route yet: search + exact fetch.
            # Once an explicit corroboration route exists its requests replace
            # that reservation. Never infer independence from provider confidence.
            independent = [a for a in actions if a.get("provider_source_role") == "INDEPENDENT"
                       or (a.get("provenance_requirements") or {}).get("required_role") == "INDEPENDENT"
                       or a.get("event_lead_feedback")]
            if path.get('required_roles') == ['PRIMARY']:
                pass
            elif not independent:
                count += 2
            else:
                queries = [a for a in independent if not a.get('target')]
                for query in queries:
                    if not any(a.get('target') and a.get('event_lead_feedback')
                               and a.get('query') == query.get('query') for a in independent):
                        count += 1  # an unresolved-role query needs its own exact result
                if not queries and not any(a.get('target') for a in independent):
                    count += 1
            if actions and not any(a.get('target') for a in actions):
                count += 1  # a fallback search still needs its primary artifact
        return count

    def check_capacity(self, remaining, general_reserved=0):
        minimum = self.minimum() + general_reserved
        self.data["minimum_remaining_required_actions"] = minimum
        self.data["remaining_execution_capacity"] = remaining
        self.data["blocker"] = CAPACITY_BLOCK if minimum > remaining or self.data['allowance_blockers'] else None
        return self.data["blocker"]

    def completed(self, action):
        if action["action_id"] not in self.data["completed_action_ids"]:
            self.data["completed_action_ids"].append(action["action_id"])

    def qualified_primary_policy(self, action, policy, observation):
        """Called only after normal exact PRIMARY qualification, never discovery."""
        identity = action.get('acquisition_path_id')
        if (identity and policy.get('required_roles') == ['PRIMARY'] and not policy.get('risky_claim_protection')
                and policy.get('claim_type') in {'DIRECT_OFFICIAL_ACTION', 'ROUTINE_VERIFIED_FACT'}
                and observation.get('content_hash') and observation.get('exact_artifact_reached')
                and (observation.get('post_fetch_qualification') or {}).get('state') == 'ELIGIBLE_OBSERVATION'
                and (observation.get('source_role_resolution') or {}).get('evidence_role') == 'PRIMARY'
                and (observation.get('temporal_relevance') or {}).get('active_on_edition_date') is True):
            self.data['paths'][identity]['required_roles'] = ['PRIMARY']
            self.data['paths'][identity]['qualified_policy_proof'] = {
                'observation_id':observation['observation_id'], 'content_hash':observation['content_hash'],
                'policy':deepcopy(policy)}

    def reject(self, action, reason):
        identity = action.get("acquisition_path_id")
        if identity and identity in self.data["paths"]:
            path = self.data["paths"][identity]
            path["state"] = "FAILED"
            path["failure_reasons"].append({"action_id": action["action_id"], "reason": reason})
            self.promote()

    def report(self):
        return deepcopy(self.data)

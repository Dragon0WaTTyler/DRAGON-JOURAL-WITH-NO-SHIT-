from __future__ import annotations

from pathlib import Path
import sys

from dragon.providers import (
    LocalCommandEditorialProvider,
    ProviderError,
    SECTION_HEADINGS,
    UnconfiguredEditorialProvider,
    editorial_provider_from_config,
)


def _provider_script(path: Path) -> None:
    sections = repr(SECTION_HEADINGS)
    path.write_text(
        """import argparse, json, sys
SECTION_HEADINGS=__SECTIONS__
p=argparse.ArgumentParser(); p.add_argument('--operation', required=True); a=p.parse_args()
payload=json.load(sys.stdin)
if a.operation == 'healthcheck':
    value={'status':'PASS','unattended':True,'provider':'test-local'}
elif a.operation == 'research':
    value={'edition_date':payload['edition_date'],'sources':[{'id':'s1','url':'https://example.org/exact-page','publisher':'مصدر اختباري','publication_date':'2099-01-02','accessed_at':'2099-01-02T07:00:00+01:00','source_type':'primary','claim_supported':'ادعاء اختباري'}]}
elif a.operation == 'articles':
    words='كلمة عربية موثقة ' * 1400
    elements={key:'عنصر تحريري موثق' for key in ('lead','nut_graf','verified_facts','context','uncertainty','consequences','next_steps')}
    value=[]
    for index,(key,heading) in enumerate(SECTION_HEADINGS):
        if index == 0:
            value.append({'id':'a1','section_id':key,'section':heading,'status':'ACTIVE','headline':'عنوان عربي اختباري','standfirst':'مقدمة عربية واضحة','byline':'تحرير: DRAGON','body':[words],'source_ids':['s1'],'editorial_elements':elements})
        else:
            value.append({'section_id':key,'section':heading,'status':'SKIPPED','skip_reason':'لا توجد مادة موثقة بما يكفي في هذا الاختبار'})
else:
    raise SystemExit(2)
json.dump(value, sys.stdout, ensure_ascii=False)
""".replace("__SECTIONS__", sections),
        encoding="utf-8",
    )


def test_local_command_provider_health_research_and_section_decisions(tmp_path: Path) -> None:
    script = tmp_path / "provider.py"
    _provider_script(script)
    provider = LocalCommandEditorialProvider((sys.executable, str(script)), timeout_seconds=30)
    assert provider.healthcheck()["unattended"] is True
    research = provider.research("2099-01-02")
    assert research["sources"][0]["url"] == "https://example.org/exact-page"
    decisions = provider.articles(research)
    assert len(decisions) == 23
    assert decisions[0]["status"] == "ACTIVE"
    assert all(item["status"] == "SKIPPED" for item in decisions[1:])


def test_provider_factory_cannot_claim_availability_before_proven_check(tmp_path: Path) -> None:
    script = tmp_path / "provider.py"
    _provider_script(script)
    config = {
        "providers": {
            "ai": {
                "type": "local-command",
                "integration_test_status": "NOT_RUN",
                "command": [sys.executable, str(script)],
            }
        }
    }
    assert isinstance(editorial_provider_from_config(config), UnconfiguredEditorialProvider)
    assert isinstance(
        editorial_provider_from_config(config, require_proven=False),
        LocalCommandEditorialProvider,
    )


def test_provider_rejects_homepage_as_exact_research_evidence(tmp_path: Path) -> None:
    script = tmp_path / "bad-provider.py"
    script.write_text(
        "import json,sys; p=json.load(sys.stdin); json.dump({'edition_date':p['edition_date'],'sources':[{'id':'s','url':'https://example.org/'}]},sys.stdout)",
        encoding="utf-8",
    )
    provider = LocalCommandEditorialProvider((sys.executable, str(script)), timeout_seconds=30)
    try:
        provider.research("2099-01-02")
    except ProviderError as exc:
        assert exc.code == "RESEARCH_PACKET_INVALID"
    else:
        raise AssertionError("homepage was accepted as exact evidence")

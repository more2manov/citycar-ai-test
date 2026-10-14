import re

import pytest
import responses

import amocrm_problem_deals as m

NOW = 1_700_000_000
DAY = 86400
BASE = "https://demo.amocrm.ru/api/v4/"
TASKS, LEADS = re.compile(BASE + "tasks"), re.compile(BASE + "leads")


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AMO_SUBDOMAIN", "demo")
    monkeypatch.setenv("AMO_TOKEN", "test-token")
    monkeypatch.setattr(m.time, "sleep", lambda s: None)


def lead(id_, status=1):
    return {"id": id_, "name": f"Сделка {id_}", "responsible_user_id": 7, "status_id": status}


def task(lead_id, till):
    return {"entity_id": lead_id, "complete_till": till}


def page(key, items, next_url=None):
    body = {"_embedded": {key: items}}
    if next_url:
        body["_links"] = {"next": {"href": next_url}}
    return body


@responses.activate
def test_lead_without_tasks():
    responses.add(responses.GET, TASKS, json=page("tasks", []))
    responses.add(responses.GET, LEADS, json=page("leads", [lead(1)]))
    assert m.problem_deals(NOW) == [(1, "Сделка 1", 7, "нет задач")]


@responses.activate
def test_overdue_task_uses_min_complete_till():
    responses.add(responses.GET, TASKS, json=page("tasks", [
        task(2, NOW - 3 * DAY), task(2, NOW - DAY), task(2, NOW + DAY)]))
    responses.add(responses.GET, LEADS, json=page("leads", [lead(2)]))
    assert m.problem_deals(NOW) == [(2, "Сделка 2", 7, "просрочена (3 дн.)")]


@responses.activate
def test_future_task_is_not_problem():
    responses.add(responses.GET, TASKS, json=page("tasks", [task(3, NOW + DAY)]))
    responses.add(responses.GET, LEADS, json=page("leads", [lead(3)]))
    assert m.problem_deals(NOW) == []


@responses.activate
@pytest.mark.parametrize("status", [142, 143])
def test_closed_lead_skipped(status):
    responses.add(responses.GET, TASKS, json=page("tasks", []))
    responses.add(responses.GET, LEADS, json=page("leads", [lead(4, status)]))
    assert m.problem_deals(NOW) == []


@responses.activate
def test_pagination_two_pages():
    responses.add(responses.GET, TASKS, status=204)
    responses.add(responses.GET, LEADS, json=page("leads", [lead(5)], next_url=BASE + "leads?page=2"))
    responses.add(responses.GET, LEADS, json=page("leads", [lead(6)]))
    assert [r[0] for r in m.problem_deals(NOW)] == [5, 6]
    pages = [c.request.params["page"] for c in responses.calls if "/leads?" in c.request.url]
    assert pages == ["1", "2"]


@responses.activate
def test_retry_on_429():
    responses.add(responses.GET, TASKS, json=page("tasks", []))
    responses.add(responses.GET, LEADS, status=429, headers={"Retry-After": "1"})
    responses.add(responses.GET, LEADS, json=page("leads", [lead(7)]))
    assert m.problem_deals(NOW) == [(7, "Сделка 7", 7, "нет задач")]
    assert sum("/leads?" in c.request.url for c in responses.calls) == 2


@responses.activate
def test_auth_header():
    responses.add(responses.GET, TASKS, json=page("tasks", []))
    responses.add(responses.GET, LEADS, json=page("leads", []))
    m.problem_deals(NOW)
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-token"

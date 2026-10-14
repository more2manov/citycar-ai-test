"""Открытые сделки amoCRM без задач или с просроченными задачами."""
import os
import time

import requests

CLOSED = {142, 143}  # успешно реализовано / закрыто и не реализовано


def fetch(path, params):
    """Обходит страницы API v4; пауза 0.2 с, при 429 ждёт и повторяет."""
    url = f"https://{os.environ['AMO_SUBDOMAIN']}.amocrm.ru/api/v4/{path}"
    headers = {"Authorization": f"Bearer {os.environ['AMO_TOKEN']}"}
    page = 1
    while True:
        time.sleep(0.2)
        r = requests.get(url, headers=headers, timeout=30,
                         params={**params, "limit": 250, "page": page})
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 1)))
            continue
        if r.status_code == 204:
            return
        r.raise_for_status()
        data = r.json()
        yield from data["_embedded"][path]
        if "next" not in data.get("_links", {}):
            return
        page += 1


def problem_deals(now=None):
    now, due, rows = now or time.time(), {}, []
    for t in fetch("tasks", {"filter[is_completed]": 0, "filter[entity_type]": "leads"}):
        due[t["entity_id"]] = min(t["complete_till"], due.get(t["entity_id"], t["complete_till"]))
    for d in fetch("leads", {}):
        till = due.get(d["id"])
        if d["status_id"] in CLOSED or (till is not None and till >= now):
            continue
        reason = "нет задач" if till is None else f"просрочена ({int((now - till) // 86400)} дн.)"
        rows.append((d["id"], d["name"], d["responsible_user_id"], reason))
    return rows


if __name__ == "__main__":
    for row in problem_deals():
        print(*row, sep="\t")

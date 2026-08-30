from fastapi.testclient import TestClient

from backend import main
from backend.tests.conftest import CSRF_HEADERS


def register(client, username="alice", password="correcthorse"):
    return client.post(
        "/api/auth/register", json={"username": username, "password": password}, headers=CSRF_HEADERS
    )


def login(client, username="alice", password="correcthorse"):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}, headers=CSRF_HEADERS
    )


# --- 127.0.0.1 -> localhost redirect ----------------------------------
#
# Safari doesn't treat http://127.0.0.1 as a secure context for `Secure`
# cookies (unlike Chrome/Firefox and unlike http://localhost), so the
# session cookie set on login/register never actually gets stored there -
# every later request looks logged-out. See backend/main.py's
# redirect_127_to_localhost middleware.


def test_127_0_0_1_is_redirected_to_localhost_preserving_method_and_path():
    client_127 = TestClient(main.app, base_url="http://127.0.0.1", follow_redirects=False)
    res = client_127.post(
        "/api/auth/login", json={"username": "alice", "password": "x"}, headers=CSRF_HEADERS
    )
    assert res.status_code == 307
    assert res.headers["location"] == "http://localhost/api/auth/login"


def test_localhost_is_not_redirected():
    client_localhost = TestClient(main.app, base_url="http://localhost", follow_redirects=False)
    res = client_localhost.get("/api/mode")
    assert res.status_code == 200


# --- auth flow -------------------------------------------------------


def test_session_cookie_omits_secure_flag_over_plain_http():
    # Safari, unlike Chrome/Firefox, silently drops a `Secure` cookie set
    # over plain HTTP even on localhost - the session would never round
    # trip and every later request would look logged-out (401). Chrome and
    # Firefox store it either way, so leaving the flag off costs nothing
    # for a real (HTTPS) deployment while fixing Safari in local dev.
    client_http = TestClient(main.app, base_url="http://localhost")
    res = register(client_http)
    assert res.status_code == 200
    assert "Secure" not in res.headers["set-cookie"]


def test_register_sets_httponly_session_cookie(client):
    res = register(client)
    assert res.status_code == 200
    assert res.json() == {"username": "alice"}
    assert "session" in res.cookies
    set_cookie = res.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=strict" in set_cookie.lower().replace("samesite=strict", "SameSite=strict")


def test_register_without_csrf_header_is_rejected(client):
    res = client.post("/api/auth/register", json={"username": "alice", "password": "correcthorse"})
    assert res.status_code == 403


def test_register_duplicate_username_conflicts(client):
    register(client)
    res = register(client)
    assert res.status_code == 409


def test_register_rejects_invalid_username_or_password(client):
    assert register(client, username="ab", password="correcthorse").status_code == 400
    assert register(client, username="validname", password="short").status_code == 400


def test_login_with_correct_credentials_succeeds(client):
    register(client)
    res = login(client)
    assert res.status_code == 200
    assert "session" in res.cookies


def test_login_with_wrong_password_fails(client):
    register(client)
    res = login(client, password="wrongpassword")
    assert res.status_code == 401


def test_me_requires_a_session_cookie(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_logged_in_username(client):
    register(client)
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json() == {"username": "alice"}


def test_logout_clears_the_session(client):
    register(client)
    res = client.post("/api/auth/logout", headers=CSRF_HEADERS)
    assert res.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_csrf_header_is_rejected(client):
    register(client)
    res = client.post("/api/auth/logout")
    assert res.status_code == 403
    # session must still be alive - the logout never actually ran
    assert client.get("/api/auth/me").status_code == 200


# --- rate limiting -----------------------------------------------------


def test_login_is_rate_limited_per_ip(client):
    register(client)
    for _ in range(10):
        res = login(client, password="wrongpassword")
        assert res.status_code == 401
    res = login(client, password="wrongpassword")
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0


def test_register_is_rate_limited_per_ip(client):
    for i in range(5):
        res = register(client, username=f"user{i}", password="correcthorse")
        assert res.status_code == 200
    res = register(client, username="user_over_limit", password="correcthorse")
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0


# --- chat ---------------------------------------------------------------


def test_chat_requires_login(client):
    res = client.post(
        "/api/chat", json={"message": "pectoraux", "lang": "fr", "history": []}, headers=CSRF_HEADERS
    )
    assert res.status_code == 401


def test_chat_without_csrf_header_is_rejected(client):
    register(client)
    res = client.post("/api/chat", json={"message": "pectoraux", "lang": "fr", "history": []})
    assert res.status_code == 403


def test_chat_works_when_logged_in(client):
    register(client)
    res = client.post(
        "/api/chat", json={"message": "pectoraux avec halteres", "lang": "fr", "history": []}, headers=CSRF_HEADERS
    )
    assert res.status_code == 200
    body = res.json()
    assert "message" in body
    assert isinstance(body["exercises"], list)


def test_chat_is_rate_limited_per_user(client):
    register(client)
    for _ in range(20):
        res = client.post(
            "/api/chat", json={"message": "pectoraux", "lang": "fr", "history": []}, headers=CSRF_HEADERS
        )
        assert res.status_code == 200
    res = client.post(
        "/api/chat", json={"message": "pectoraux", "lang": "fr", "history": []}, headers=CSRF_HEADERS
    )
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0


# --- misc -----------------------------------------------------------------


def test_healthz_is_public_and_ok(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# --- plan CRUD ------------------------------------------------------------


def _sample_plan_body(exercise_id):
    return {
        "lang": "fr",
        "days": [
            {
                "weekday": "monday",
                "label": "Push",
                "exercises": [
                    {"exercise_id": exercise_id, "sets": 3, "reps": "8-12", "rest_seconds": 90, "done": False}
                ],
            }
        ],
    }


def _real_exercise_id():
    import scripting as s

    return s.load_exercises()[0]["id"]


def test_plan_requires_login(client):
    assert client.get("/api/plan").status_code == 401


def test_plan_put_get_delete_roundtrip(client):
    register(client)
    exercise_id = _real_exercise_id()

    put_res = client.put("/api/plan", json=_sample_plan_body(exercise_id), headers=CSRF_HEADERS)
    assert put_res.status_code == 200

    get_res = client.get("/api/plan")
    assert get_res.status_code == 200
    assert get_res.json()["days"][0]["exercises"][0]["exercise"]["id"] == exercise_id

    delete_res = client.delete("/api/plan", headers=CSRF_HEADERS)
    assert delete_res.status_code == 200
    assert client.get("/api/plan").status_code == 404


def test_plan_put_without_csrf_header_is_rejected(client):
    register(client)
    exercise_id = _real_exercise_id()
    res = client.put("/api/plan", json=_sample_plan_body(exercise_id))
    assert res.status_code == 403


def test_plan_put_rejects_duplicate_exercise_in_same_day(client):
    register(client)
    exercise_id = _real_exercise_id()
    body = _sample_plan_body(exercise_id)
    body["days"][0]["exercises"].append(body["days"][0]["exercises"][0])
    res = client.put("/api/plan", json=body, headers=CSRF_HEADERS)
    assert res.status_code == 400


def test_plan_put_rejects_unknown_exercise_id(client):
    register(client)
    body = _sample_plan_body("not-a-real-exercise-id")
    res = client.put("/api/plan", json=body, headers=CSRF_HEADERS)
    assert res.status_code == 400


def test_plan_put_rejects_sets_out_of_bounds(client):
    register(client)
    body = _sample_plan_body(_real_exercise_id())
    body["days"][0]["exercises"][0]["sets"] = 999
    res = client.put("/api/plan", json=body, headers=CSRF_HEADERS)
    assert res.status_code == 422


def test_plan_put_rejects_negative_rest_seconds(client):
    register(client)
    body = _sample_plan_body(_real_exercise_id())
    body["days"][0]["exercises"][0]["rest_seconds"] = -1
    res = client.put("/api/plan", json=body, headers=CSRF_HEADERS)
    assert res.status_code == 422


def test_mark_exercise_done(client):
    register(client)
    exercise_id = _real_exercise_id()
    client.put("/api/plan", json=_sample_plan_body(exercise_id), headers=CSRF_HEADERS)

    res = client.patch(
        "/api/plan/exercise/done",
        json={"day_index": 0, "exercise_id": exercise_id, "done": True},
        headers=CSRF_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["days"][0]["exercises"][0]["done"] is True


def test_swap_plan_exercise(client):
    register(client)
    exercise_id = _real_exercise_id()
    client.put("/api/plan", json=_sample_plan_body(exercise_id), headers=CSRF_HEADERS)

    res = client.post(
        "/api/plan/exercise/swap",
        json={"day_index": 0, "exercise_id": exercise_id},
        headers=CSRF_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["days"][0]["exercises"][0]["exercise"]["id"] != exercise_id


def test_a_second_users_plan_is_isolated(client):
    exercise_id = _real_exercise_id()
    register(client, username="alice")
    client.put("/api/plan", json=_sample_plan_body(exercise_id), headers=CSRF_HEADERS)

    client.post("/api/auth/logout", headers=CSRF_HEADERS)
    register(client, username="bob")
    assert client.get("/api/plan").status_code == 404


# --- security headers ------------------------------------------------------


def test_security_headers_present_on_every_response(client):
    res = client.get("/api/mode")
    assert "script-src 'self'" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"

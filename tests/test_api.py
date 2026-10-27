"""API tests for the TECHSPARK chatbot backend (Gemini calls are mocked)."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from api import index


@pytest.fixture
def client():
    return TestClient(index.app)


@pytest.fixture(autouse=True)
def reset_rate_limit_store():
    index._rate_limit_store.clear()
    yield
    index._rate_limit_store.clear()


@pytest.fixture(autouse=True)
def configured_gemini_api_key(monkeypatch):
    monkeypatch.setattr(index, "GEMINI_API_KEY", "test-gemini-key")


def make_response(text=None, block_reason=None):
    return SimpleNamespace(
        text=text,
        prompt_feedback=SimpleNamespace(block_reason=block_reason),
    )


class FakeModels:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.exc is not None:
            raise self.exc
        return self.response


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.api_key = "fake-key"
        self.models = FakeModels(response=response, exc=exc)


class GeminiMock:
    def __init__(self, monkeypatch):
        self.state = {"response": None, "exc": None}
        self.clients = []

        def factory(**kwargs):
            client = FakeClient(response=self.state["response"], exc=self.state["exc"])
            self.clients.append(client)
            return client

        monkeypatch.setattr(index.genai, "Client", factory)

    def set_response(self, text=None, block_reason=None):
        self.state["response"] = make_response(text=text, block_reason=block_reason)
        self.state["exc"] = None

    def set_exception(self, exc):
        self.state["exc"] = exc
        self.state["response"] = None

    @property
    def last_client(self):
        return self.clients[-1] if self.clients else None


@pytest.fixture
def gemini_mock(monkeypatch):
    return GeminiMock(monkeypatch)


def post_question(client, question):
    return client.post("/api/chat", json={"question": question})


class TestHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestChatValidation:
    def test_empty_question_is_rejected(self, client):
        response = client.post("/api/chat", json={"question": ""})
        assert response.status_code == 422

    def test_whitespace_only_question_is_rejected(self, client):
        response = client.post("/api/chat", json={"question": "    \t\n  "})
        assert response.status_code == 422

    def test_overly_long_question_is_rejected(self, client):
        response = client.post("/api/chat", json={"question": "a" * 1001})
        assert response.status_code == 422

    def test_question_at_max_length_is_accepted(self, client, gemini_mock):
        gemini_mock.set_response("The fest starts on August 22, 2025.")
        response = client.post("/api/chat", json={"question": "a" * 1000})
        assert response.status_code == 200


class TestChatSuccess:
    def test_valid_question_returns_expected_response_structure(
        self, client, gemini_mock
    ):
        gemini_mock.set_response(
            "The fest features CodeStorm, RoboRush, Brainwave, and DesignSprint."
        )
        response = post_question(client, "What events are available?")

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"answer"}
        assert (
            body["answer"]
            == "The fest features CodeStorm, RoboRush, Brainwave, and DesignSprint."
        )

        fake_client = gemini_mock.last_client
        assert fake_client is not None
        call = fake_client.models.calls[-1]
        assert call["model"] == index.GEMINI_MODEL
        assert "TECHSPARK" in call["config"].system_instruction
        assert "CodeStorm" in call["contents"]
        assert "What events are available?" in call["contents"]


class TestChatErrorHandling:
    def test_missing_api_key_returns_service_unavailable(
        self, client, gemini_mock, monkeypatch
    ):
        monkeypatch.setattr(index, "GEMINI_API_KEY", None)
        response = post_question(client, "When is the fest?")

        assert response.status_code == 503
        assert response.json()["answer"]
        assert gemini_mock.clients == []

    def test_gemini_rate_limit_is_handled(self, client, gemini_mock):
        gemini_mock.set_exception(genai_errors.APIError(code=429, response_json={}))
        response = post_question(client, "What is the registration fee?")

        assert response.status_code == 503
        assert response.json()["answer"]

    def test_gemini_timeout_is_handled(self, client, gemini_mock):
        gemini_mock.set_exception(TimeoutError("The request timed out."))
        response = post_question(client, "When is the fest?")

        assert response.status_code == 503
        assert response.json()["answer"]

    def test_gemini_empty_response_is_handled(self, client, gemini_mock):
        gemini_mock.set_response(text=None)
        response = post_question(client, "What events are available?")

        assert response.status_code == 200
        assert response.json()["answer"]

    def test_unexpected_provider_error_is_handled_safely(
        self, client, gemini_mock
    ):
        gemini_mock.set_exception(RuntimeError("boom: secret-token-12345 failed"))
        response = post_question(client, "How can I contact the organizers?")

        assert response.status_code == 503
        body = response.json()
        assert body["answer"]
        assert "secret-token-12345" not in json.dumps(body)

    def test_invalid_fest_json_is_handled_safely(
        self, client, gemini_mock, tmp_path, monkeypatch
    ):
        invalid_path = tmp_path / "fest_data.json"
        invalid_path.write_text("{ not valid json !!!", encoding="utf-8")
        monkeypatch.setattr(index, "FEST_DATA_PATH", invalid_path)

        response = post_question(client, "What events are available?")

        assert response.status_code == 503
        assert response.json()["answer"]

    def test_missing_system_prompt_is_handled_safely(
        self, client, gemini_mock, tmp_path, monkeypatch
    ):
        missing_path = tmp_path / "system_prompt.txt"
        monkeypatch.setattr(index, "SYSTEM_PROMPT_PATH", missing_path)

        response = post_question(client, "What events are available?")

        assert response.status_code == 503
        assert response.json()["answer"]


class TestChatBehavior:
    def test_unrelated_question_triggers_refusal(self, client, gemini_mock):
        gemini_mock.set_response("This should not be called.")
        response = post_question(client, "What is the capital of France?")

        assert response.status_code == 200
        body = response.json()
        assert "TECHSPARK" in body["answer"]
        assert gemini_mock.clients == []

    def test_missing_fest_info_does_not_invent_details(
        self, client, gemini_mock
    ):
        gemini_mock.set_response("Sorry, the information is not currently available.")
        response = post_question(client, "Who is the chief guest?")

        assert response.status_code == 200
        assert response.json()["answer"] == (
            "Sorry, the information is not currently available."
        )

    def test_rate_limit_returns_temporary_unavailability(
        self, client, gemini_mock, monkeypatch
    ):
        monkeypatch.setattr(index, "RATE_LIMIT_MAX_REQUESTS", 2)
        monkeypatch.setattr(index, "RATE_LIMIT_WINDOW_SECONDS", 60)

        first = post_question(client, "When is the fest?")
        second = post_question(client, "What events are available?")
        third = post_question(client, "What is the registration fee?")

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert "too many questions" in third.json()["answer"].lower()

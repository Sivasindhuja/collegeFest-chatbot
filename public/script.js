
const API_URL = "http://127.0.0.1:8000/api/chat";

const WELCOME_MESSAGE =
  "Hi there! I'm the TECHSPARK assistant. Ask me about the fest dates, events, speakers, registration, fees, rules or anything else related to TECHSPARK!";

const SUGGESTED_QUESTIONS = [
  "When is the fest?",
  "What events are available?",
  "What is the registration fee?",
  "Who are the guest speakers?",
  "How can I contact the organizers?",
];

const SERVICE_UNAVAILABLE_MESSAGE =
  "Sorry, the fest assistant is temporarily unavailable. Please try again shortly.";

const state = {
  isLoading: false,
};

const messagesEl = document.getElementById("messages");
const typingIndicatorEl = document.getElementById("typing-indicator");
const suggestionsEl = document.getElementById("suggestions");
const chatForm = document.getElementById("chat-form");
const questionInput = document.getElementById("question-input");
const sendButton = document.getElementById("send-button");

function createElement(tag, className) {
  const el = document.createElement(tag);

  if (className) {
    el.className = className;
  }

  return el;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(role, text, isError = false) {
  const row = createElement(
    "div",
    `message ${role}${isError ? " error" : ""}`
  );

  const bubble = createElement("div", "message-text");
  bubble.textContent = text;

  row.appendChild(bubble);
  messagesEl.appendChild(row);

  scrollToBottom();
}

function showTypingIndicator() {
  typingIndicatorEl.hidden = false;
  scrollToBottom();
}

function hideTypingIndicator() {
  typingIndicatorEl.hidden = true;
}

function clearConversation() {
  messagesEl.innerHTML = "";

  state.isLoading = false;
  sendButton.disabled = false;
  questionInput.disabled = false;

  hideTypingIndicator();
  addMessage("bot", WELCOME_MESSAGE);
}

function renderSuggestions() {
  suggestionsEl.innerHTML = "";

  SUGGESTED_QUESTIONS.forEach((question) => {
    const chip = createElement("button", "suggestion-chip");

    chip.type = "button";
    chip.textContent = question;

    chip.addEventListener("click", () => {
      sendQuestion(question);
    });

    suggestionsEl.appendChild(chip);
  });
}

function setLoading(isLoading) {
  state.isLoading = isLoading;

  sendButton.disabled = isLoading;
  questionInput.disabled = isLoading;

  if (isLoading) {
    showTypingIndicator();
  } else {
    hideTypingIndicator();
  }
}

async function sendQuestion(question) {
  const trimmed = (question || "").trim();

  if (!trimmed || state.isLoading) {
    return;
  }

  addMessage("user", trimmed);

  setLoading(true);
  questionInput.value = "";

  let data = null;
  let responseOk = false;

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: trimmed,
      }),
    });

    responseOk = response.ok;

    try {
      data = await response.json();
    } catch (error) {
      console.error("Could not parse API response:", error);
      data = null;
    }
  } catch (error) {
    console.error("Chat API request failed:", error);

    setLoading(false);

    addMessage(
      "bot",
      "Could not connect to the chatbot API. Make sure the FastAPI server is running at http://127.0.0.1:8000 and that CORS is configured correctly.",
      true
    );

    return;
  }

  setLoading(false);

  if (!responseOk) {
    console.error("Chat API returned an error:", data);

    const serverAnswer =
      data && typeof data.answer === "string"
        ? data.answer
        : "";

    addMessage(
      "bot",
      serverAnswer || SERVICE_UNAVAILABLE_MESSAGE,
      true
    );

    return;
  }

  const answer = data ? data.answer : "";

  if (typeof answer !== "string" || !answer.trim()) {
    addMessage("bot", SERVICE_UNAVAILABLE_MESSAGE, true);
    return;
  }

  addMessage("bot", answer);
}

function handleSubmit(event) {
  event.preventDefault();

  if (state.isLoading) {
    return;
  }

  const value = questionInput.value;

  if (!value.trim()) {
    return;
  }

  sendQuestion(value);
}

function init() {
  clearConversation();
  renderSuggestions();

  chatForm.addEventListener("submit", handleSubmit);

  sendButton.addEventListener("click", () => {
    if (state.isLoading) {
      return;
    }

    if (questionInput.value.trim()) {
      sendQuestion(questionInput.value);
    }
  });

  document
    .getElementById("clear-button")
    .addEventListener("click", () => {
      if (!state.isLoading) {
        clearConversation();
      }
    });

  questionInput.addEventListener("input", () => {
    questionInput.value = questionInput.value.slice(0, 1000);
  });

  scrollToBottom();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

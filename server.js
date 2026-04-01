import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import fetch from "node-fetch";

dotenv.config();
const app = express();
const PORT = 5000;

app.use(cors({ origin: "http://localhost:3000" }));
app.use(express.json());


const festInfo = `
Welcome to Celestra 2025 — the annual inter-college tech fest hosted by SPMVV!

📅 Dates: August 22–24, 2025
📍 Venue: SPMVV Campus, Tirupati

 Events:
1. CodeStorm — Hackathon with prizes up to ₹50,000.
2. RoboRush — Robotics competition.
3. Brainwave — Technical quiz.
4. DesignSprint — UI/UX design challenge.

Speakers:
- Dr. Kavya Ramesh (AI Researcher, Google DeepMind)
- Mr. Arjun Mehta (CTO, InnovateX)
- Ms. Sneha Rao (Product Designer, Microsoft)

Registration:
- Open until August 20, 2025
- Fee: ₹200 (includes kit + lunch)
- Register: techspark-spmvv.in/register

Rules:
- College ID required
- Teams must register in advance
- Misconduct = disqualification

Contacts:
- Email: celestra@spmvv.ac.in
- Phone: +91 9000000001
- Instagram: @celestra_spmvv
`;


app.post("/query", async (req, res) => {
  const { question } = req.body;
  const apiKey = process.env.OPENROUTER_API_KEY;

  try {
    const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "openai/gpt-4o-mini",
        messages: [
          { role: "system", content: "You are a chatbot for Celestra 2025. Only answer using fest info. If irrelevant, say 'I can only answer Celestra questions.'" },
          { role: "user", content: `Fest Info:\n${festInfo}` },
          { role: "user", content: `Question: ${question}` },
        ],
      }),
    });

    const data = await response.json();
    const answer = data.choices?.[0]?.message?.content || "No answer available.";

    res.json({ answer });
  } catch (err) {
    console.error(err);
    res.status(500).json({ answer: "Error contacting OpenRouter API." });
  }
});

app.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);
});
3
const form = document.getElementById("analyzerForm");
const statusBox = document.getElementById("statusBox");
const resultsSection = document.getElementById("resultsSection");

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const formData = new FormData(form);
  showStatus("Analyzing resume...", "info");
  resultsSection.classList.add("d-none");

  try {
    const response = await fetch("/analyze", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();
    console.log("API RESPONSE:", data);

    if (!response.ok) {
      throw new Error(data.error || "Something went wrong.");
    }

    renderResults(data);
    showStatus("Analysis completed successfully.", "success");
    resultsSection.classList.remove("d-none");
  } catch (error) {
    showStatus(error.message, "danger");
  }
});

function showStatus(message, type) {
  statusBox.className = `alert alert-${type} mt-4`;
  statusBox.textContent = message;
  statusBox.classList.remove("d-none");
}

function renderResults(data) {
  setText("overallScore", data.overall_score ?? 0);
  setText("candidateName", data.candidate_name || "Candidate");
  setText(
    "candidateSummary",
    data.candidate_summary || "No summary available.",
  );
  setText("confidenceScore", data.confidence_score ?? "N/A");
  setText(
    "recommendationReason",
    data.recommendation_reason || "No reason available.",
  );
  setText(
    "recruiterSummary",
    data.recruiter_summary || "No recruiter summary available.",
  );
  setText("matchScore", data.job_match_analysis?.match_score ?? 0);
  setText("keywordCoverage", data.job_match_analysis?.keyword_coverage ?? 0);
  setText("atsScore", data.resume_quality?.ats_score ?? 0);

  renderRecommendation(data.hiring_recommendation);
  renderFeedback(data.feedback);
  renderScoreBreakdown(data.score_breakdown);
  renderAdaptiveQuestions(data.adaptive_question_difficulty);
  renderQuestions(data.dynamic_questions);
  renderSkills(data.job_match_analysis);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function renderRecommendation(recommendation) {
  const el = document.getElementById("recommendationBlock");
  if (!el) return;

  el.innerHTML = `
    <div class="metric-chip">${recommendation || "Not Available"}</div>
  `;
}

function renderFeedback(feedback) {
  const strengths = (feedback?.strengths || [])
    .map((item) => `<li>${item}</li>`)
    .join("");

  const improvements = (feedback?.improvements || [])
    .map((item) => `<li>${item}</li>`)
    .join("");

  const strengthsBlock = document.getElementById("strengthsBlock");
  const improvementsBlock = document.getElementById("improvementsBlock");

  if (strengthsBlock) {
    strengthsBlock.innerHTML = `
      <h4>Strengths</h4>
      <ul>${strengths || "<li>No strengths detected</li>"}</ul>
    `;
  }

  if (improvementsBlock) {
    improvementsBlock.innerHTML = `
      <h4>Improvements</h4>
      <ul>${improvements || "<li>No improvements suggested</li>"}</ul>
    `;
  }
}

function renderScoreBreakdown(scoreBreakdown) {
  const container = document.getElementById("scoreBreakdown");
  if (!container) return;

  const html = (scoreBreakdown || [])
    .map(
      (item) => `
        <div class="question-item">
          <strong>${item.label}: ${item.score}</strong>
        </div>
      `,
    )
    .join("");

  container.innerHTML = html || "<p>No score breakdown available</p>";
}

function renderAdaptiveQuestions(questions) {
  const container = document.getElementById("adaptiveQuestions");
  if (!container) return;

  const html = (questions || [])
    .map(
      (q) => `
        <div class="question-item">
          <strong>${q.level}: ${q.question}</strong>
          <p class="mb-0 mt-2">${q.purpose}</p>
        </div>
      `,
    )
    .join("");

  container.innerHTML = html || "<p>No adaptive questions generated</p>";
}

function renderQuestions(questions) {
  const container = document.getElementById("followUpQuestions");
  if (!container) return;

  const html = (questions || [])
    .map(
      (q, i) => `
        <div class="question-item">
          <strong>Q${i + 1}. ${q.question}</strong>
          <p class="mb-0 mt-2">${q.purpose}</p>
        </div>
      `,
    )
    .join("");

  container.innerHTML = html || "<p>No questions generated</p>";
}

function renderSkills(jobMatch) {
  const matched = document.getElementById("matchedSkills");
  const missing = document.getElementById("missingSkills");

  if (matched) {
    matched.innerHTML =
      (jobMatch?.matched_skills || [])
        .map((skill) => `<span class="skill-chip">${skill}</span>`)
        .join("") || "<p>No matched skills</p>";
  }

  if (missing) {
    missing.innerHTML =
      (jobMatch?.missing_skills || [])
        .map((skill) => `<span class="skill-chip muted">${skill}</span>`)
        .join("") || "<p>No missing skills</p>";
  }
}

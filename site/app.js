/* КТ Тренажёр — static quiz app.
 * Data: data/topics.json lists topics; each topic file is the questions.json
 * produced by the extraction pipeline. Only questions with a known correct
 * answer are used. Wrong answers are stored per topic in localStorage so the
 * user can retest their mistakes.
 */

const STR = {
  ru: {
    appTitle: "КТ Тренажёр",
    chooseTopic: "Выберите тему",
    back: "Назад",
    questionCount: "Количество вопросов",
    questionLang: "Язык вопросов",
    allLangs: "Все",
    allQuestions: "Все",
    startTest: "Начать тест",
    mistakes: n => `Работа над ошибками (${n})`,
    questions: n => `${n} вопросов`,
    check: "Проверить",
    next: "Дальше",
    finish: "Завершить",
    results: "Результат",
    scoreDetail: (ok, total) => `Правильно ${ok} из ${total}`,
    retestWrong: n => `Пройти ошибки ещё раз (${n})`,
    newTest: "Новый тест",
    toTopics: "К темам",
    needsReview: "⚠ вопрос может содержать ошибку",
    multiHint: "Выберите все правильные варианты",
    noQuestions: "Нет вопросов для выбранных настроек",
  },
  kz: {
    appTitle: "КТ Жаттықтырғыш",
    chooseTopic: "Тақырыпты таңдаңыз",
    back: "Артқа",
    questionCount: "Сұрақтар саны",
    questionLang: "Сұрақтар тілі",
    allLangs: "Барлығы",
    allQuestions: "Барлығы",
    startTest: "Тестті бастау",
    mistakes: n => `Қателермен жұмыс (${n})`,
    questions: n => `${n} сұрақ`,
    check: "Тексеру",
    next: "Келесі",
    finish: "Аяқтау",
    results: "Нәтиже",
    scoreDetail: (ok, total) => `${total} сұрақтан ${ok} дұрыс`,
    retestWrong: n => `Қателерді қайта өту (${n})`,
    newTest: "Жаңа тест",
    toTopics: "Тақырыптарға",
    needsReview: "⚠ сұрақта қате болуы мүмкін",
    multiHint: "Барлық дұрыс нұсқаларды таңдаңыз",
    noQuestions: "Таңдалған баптаулар үшін сұрақ жоқ",
  },
};

const KZ_LETTERS = /[әғқңөұүһі]/i;
const COUNT_OPTIONS = [10, 25, 50, "all"];

const state = {
  lang: localStorage.getItem("kt-lang") || "ru",
  topics: [],
  topic: null,        // {id, title, file}
  questions: [],      // gradable questions of current topic
  setup: { count: 25, qlang: "all" },
  quiz: null,         // {list, idx, correct, wrongIds, selected:Set, answered}
};

const $ = id => document.getElementById(id);
const t = key => STR[state.lang][key];

/* ------------------------------------------------------------ i18n */

function applyLang() {
  document.querySelectorAll("[data-str]").forEach(el => {
    const v = STR[state.lang][el.dataset.str];
    if (typeof v === "string") el.textContent = v;
  });
  document.querySelectorAll(".lang-btn").forEach(b => b.classList.remove("active"));
  $(`lang-${state.lang}`).classList.add("active");
  document.title = t("appTitle");
  renderTopics();
  if (!$("screen-setup").classList.contains("hidden")) renderSetup();
}

function setLang(lang) {
  state.lang = lang;
  localStorage.setItem("kt-lang", lang);
  applyLang();
}

/* ------------------------------------------------------ data access */

function questionLang(q) {
  return KZ_LETTERS.test(q.question) ? "kz" : "ru";
}

async function loadTopics() {
  const res = await fetch("data/topics.json");
  state.topics = await res.json();
  renderTopics();
}

async function openTopic(topic) {
  state.topic = topic;
  const res = await fetch(`data/${topic.file}`);
  const all = await res.json();
  state.questions = all.filter(
    q => q.correct_answer_indices?.length && q.options?.length >= 2
  );
  state.questions.forEach(q => { q._lang = questionLang(q); });
  showScreen("setup");
  renderSetup();
}

/* --------------------------------------------------- mistakes store */

function mistakesKey() { return `kt-mistakes-${state.topic.id}`; }

function getMistakeIds() {
  try {
    return new Set(JSON.parse(localStorage.getItem(mistakesKey()) || "[]"));
  } catch { return new Set(); }
}

function saveMistakeIds(set) {
  localStorage.setItem(mistakesKey(), JSON.stringify([...set]));
}

function recordAnswer(qid, isCorrect) {
  const ids = getMistakeIds();
  if (isCorrect) ids.delete(qid); else ids.add(qid);
  saveMistakeIds(ids);
}

/* ----------------------------------------------------------- screens */

function showScreen(name) {
  ["topics", "setup", "quiz", "results"].forEach(s =>
    $(`screen-${s}`).classList.toggle("hidden", s !== name));
}

function renderTopics() {
  const list = $("topic-list");
  list.innerHTML = "";
  state.topics.forEach(topic => {
    const btn = document.createElement("button");
    btn.className = "topic-card";
    btn.textContent = topic.title[state.lang] || topic.title.ru;
    btn.addEventListener("click", () => openTopic(topic));
    list.appendChild(btn);
  });
}

function renderSetup() {
  $("setup-topic-title").textContent =
    state.topic.title[state.lang] || state.topic.title.ru;
  $("setup-stats").textContent = t("questions")(filteredQuestions().length);

  const chips = $("count-chips");
  chips.innerHTML = "";
  COUNT_OPTIONS.forEach(c => {
    const btn = document.createElement("button");
    btn.className = "chip" + (state.setup.count === c ? " active" : "");
    btn.textContent = c === "all" ? t("allQuestions") : c;
    btn.addEventListener("click", () => { state.setup.count = c; renderSetup(); });
    chips.appendChild(btn);
  });

  document.querySelectorAll("#qlang-chips .chip").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.qlang === state.setup.qlang);
  });

  const mistakes = [...getMistakeIds()]
    .filter(id => state.questions.some(q => q.id === id));
  const mBtn = $("start-mistakes");
  mBtn.classList.toggle("hidden", mistakes.length === 0);
  mBtn.textContent = t("mistakes")(mistakes.length);
}

function filteredQuestions() {
  return state.questions.filter(
    q => state.setup.qlang === "all" || q._lang === state.setup.qlang);
}

/* Render $...$ LaTeX inside an element (math topics). No-op until KaTeX loads. */
function renderMath(el) {
  if (window.renderMathInElement) {
    window.renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  }
}

/* -------------------------------------------------------------- quiz */

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/* Shuffle options of a question, remapping correct indices. */
function prepared(q) {
  const order = shuffle(q.options.map((_, i) => i));
  return {
    id: q.id,
    question: q.question,
    needs_review: q.needs_review,
    options: order.map(i => q.options[i]),
    correct: new Set(
      q.correct_answer_indices.map(ci => order.indexOf(ci))),
  };
}

function startQuiz(pool, count) {
  let list = shuffle([...pool]);
  if (count !== "all") list = list.slice(0, count);
  if (!list.length) { alert(t("noQuestions")); return; }
  state.quiz = {
    list: list.map(prepared),
    idx: 0,
    correctCount: 0,
    wrongIds: [],
  };
  showScreen("quiz");
  renderQuestion();
}

function renderQuestion() {
  const quiz = state.quiz;
  const q = quiz.list[quiz.idx];
  quiz.selected = new Set();
  quiz.answered = false;

  $("progress-bar").style.width = `${(quiz.idx / quiz.list.length) * 100}%`;
  $("quiz-counter").textContent = `${quiz.idx + 1}/${quiz.list.length}`;
  $("review-badge").classList.toggle("hidden", !q.needs_review);
  $("q-text").textContent = q.question;
  renderMath($("q-text"));

  const isMulti = q.correct.size > 1;
  $("multi-hint").classList.toggle("hidden", !isMulti);
  $("check-btn").classList.toggle("hidden", !isMulti);
  $("check-btn").disabled = true;
  $("next-btn").classList.add("hidden");

  const box = $("options");
  box.innerHTML = "";
  q.options.forEach((text, i) => {
    const btn = document.createElement("button");
    btn.className = "option";
    btn.textContent = text;
    btn.addEventListener("click", () => onOptionClick(i, btn, isMulti));
    box.appendChild(btn);
    renderMath(btn);
  });
}

function onOptionClick(i, btn, isMulti) {
  const quiz = state.quiz;
  if (quiz.answered) return;
  if (isMulti) {
    if (quiz.selected.has(i)) quiz.selected.delete(i);
    else quiz.selected.add(i);
    btn.classList.toggle("selected");
    $("check-btn").disabled = quiz.selected.size === 0;
  } else {
    quiz.selected = new Set([i]);
    gradeCurrent();
  }
}

function gradeCurrent() {
  const quiz = state.quiz;
  const q = quiz.list[quiz.idx];
  quiz.answered = true;

  const isCorrect =
    quiz.selected.size === q.correct.size &&
    [...quiz.selected].every(i => q.correct.has(i));

  if (isCorrect) quiz.correctCount++;
  else quiz.wrongIds.push(q.id);
  recordAnswer(q.id, isCorrect);

  document.querySelectorAll("#options .option").forEach((btn, i) => {
    btn.disabled = true;
    if (q.correct.has(i)) btn.classList.add("correct");
    else if (quiz.selected.has(i)) btn.classList.add("wrong");
  });

  $("check-btn").classList.add("hidden");
  const nextBtn = $("next-btn");
  nextBtn.textContent =
    quiz.idx + 1 === quiz.list.length ? t("finish") : t("next");
  nextBtn.classList.remove("hidden");
}

function nextQuestion() {
  const quiz = state.quiz;
  if (quiz.idx + 1 === quiz.list.length) { showResults(); return; }
  quiz.idx++;
  renderQuestion();
}

/* ----------------------------------------------------------- results */

function showResults() {
  const quiz = state.quiz;
  const pct = Math.round((quiz.correctCount / quiz.list.length) * 100);
  $("score-pct").textContent = `${pct}%`;
  $("score-detail").textContent =
    t("scoreDetail")(quiz.correctCount, quiz.list.length);

  const retest = $("retest-wrong");
  retest.classList.toggle("hidden", quiz.wrongIds.length === 0);
  retest.textContent = t("retestWrong")(quiz.wrongIds.length);
  showScreen("results");
}

/* ------------------------------------------------------------- wiring */

$("lang-ru").addEventListener("click", () => setLang("ru"));
$("lang-kz").addEventListener("click", () => setLang("kz"));
$("back-to-topics").addEventListener("click", () => showScreen("topics"));
$("quit-quiz").addEventListener("click", () => { showScreen("setup"); renderSetup(); });

document.querySelectorAll("#qlang-chips .chip").forEach(btn => {
  btn.addEventListener("click", () => {
    state.setup.qlang = btn.dataset.qlang;
    renderSetup();
  });
});

$("start-test").addEventListener("click", () =>
  startQuiz(filteredQuestions(), state.setup.count));

$("start-mistakes").addEventListener("click", () => {
  const ids = getMistakeIds();
  startQuiz(state.questions.filter(q => ids.has(q.id)), "all");
});

$("check-btn").addEventListener("click", gradeCurrent);
$("next-btn").addEventListener("click", nextQuestion);

$("retest-wrong").addEventListener("click", () => {
  const ids = new Set(state.quiz.wrongIds);
  startQuiz(state.questions.filter(q => ids.has(q.id)), "all");
});

$("again-btn").addEventListener("click", () => { showScreen("setup"); renderSetup(); });
$("home-btn").addEventListener("click", () => showScreen("topics"));

applyLang();
loadTopics();

/* English Quest — prototype minimal
   Une quête : « L'entretien d'embauche », 4 compétences (écouter, lire, écrire, parler),
   série quotidienne (streak) et points (XP). Aucune donnée n'est envoyée à un serveur. */
(function () {
  "use strict";

  /* ---------- Textes de l'interface (FR / AR / EN) ---------- */
  var T = {
    fr: {
      title: "La quête : l'entretien d'embauche",
      intro: "Vous passez un entretien dans une entreprise. 4 épreuves : écouter, lire, écrire, parler. Réussissez-les pour obtenir votre badge.",
      start: "Commencer la quête", next: "Continuer", again: "Rejouer la quête",
      step: "Épreuve", of: "sur",
      listen: "Écouter", read: "Lire", write: "Écrire", speak: "Parler",
      play: "▶ Écouter la question", replay: "▶ Réécouter",
      noTTS: "Votre navigateur ne lit pas l'anglais à voix haute. Lisez le texte ci-dessous.",
      transcript: "Texte :",
      correct: "Bravo !", wrong: "Pas tout à fait. Bonne réponse en vert.",
      checkBtn: "Vérifier", writeHint: "Écrivez 2 phrases en anglais : votre prénom, votre métier ou vos études, et pourquoi vous voulez ce poste.",
      c_len: "Au moins 8 mots", c_intro: "Vous vous présentez (I am / My name is / I'm)",
      c_why: "Vous donnez une raison (because / want / would like)", c_end: "Vous terminez par un point",
      note: "Prototype : cette vérification est simple. La correction détaillée par IA viendra dans la version suivante.",
      speakHint: "Appuyez sur le micro et dites la phrase à voix haute, en anglais.",
      mic: "🎤 Parler", listening: "🎤 Je vous écoute…",
      heard: "J'ai entendu :", match: "Ressemblance :",
      noSR: "La reconnaissance vocale n'est pas disponible sur ce navigateur (essayez Chrome). Dites la phrase à voix haute, puis évaluez-vous :",
      selfOk: "Je l'ai dite correctement", selfKo: "Je dois m'entraîner",
      done: "Quête terminée !", total: "Score total", badge: "Badge obtenu : Candidat prêt pour l'entretien",
      level: "Niveau visé : A2 vers B1", pts: "points",
      streakMsg: "Série en cours (jours) :",
      micDenied: "Micro refusé ou indisponible. Autorisez le micro, ou évaluez-vous vous-même."
    },
    ar: {
      title: "المهمة: مقابلة العمل",
      intro: "أنت تجري مقابلة عمل في شركة. أربع اختبارات: الاستماع والقراءة والكتابة والمحادثة. انجح فيها لتحصل على شارتك.",
      start: "ابدأ المهمة", next: "متابعة", again: "أعد المهمة",
      step: "الاختبار", of: "من",
      listen: "الاستماع", read: "القراءة", write: "الكتابة", speak: "المحادثة",
      play: "▶ استمع إلى السؤال", replay: "▶ أعد الاستماع",
      noTTS: "متصفحك لا يقرأ الإنجليزية بصوت عال. اقرأ النص أدناه.",
      transcript: "النص:",
      correct: "أحسنت!", wrong: "ليس تماما. الإجابة الصحيحة باللون الأخضر.",
      checkBtn: "تحقق", writeHint: "اكتب جملتين بالإنجليزية: اسمك، مهنتك أو دراستك، ولماذا تريد هذه الوظيفة.",
      c_len: "8 كلمات على الأقل", c_intro: "تقدم نفسك (I am / My name is / I'm)",
      c_why: "تذكر سببا (because / want / would like)", c_end: "تنهي بنقطة",
      note: "نسخة تجريبية: هذا التحقق بسيط. سيأتي التصحيح المفصل بالذكاء الاصطناعي في النسخة القادمة.",
      speakHint: "اضغط على الميكروفون وانطق الجملة بصوت عال بالإنجليزية.",
      mic: "🎤 تحدث", listening: "🎤 أنا أستمع…",
      heard: "سمعت:", match: "التطابق:",
      noSR: "التعرف على الصوت غير متاح في هذا المتصفح (جرب Chrome). انطق الجملة بصوت عال ثم قيم نفسك:",
      selfOk: "نطقتها بشكل صحيح", selfKo: "أحتاج إلى التدريب",
      done: "انتهت المهمة!", total: "المجموع", badge: "الشارة: مترشح جاهز للمقابلة",
      level: "المستوى المستهدف: A2 نحو B1", pts: "نقطة",
      streakMsg: "أيام متتالية:",
      micDenied: "الميكروفون مرفوض أو غير متاح. اسمح به أو قيم نفسك."
    },
    en: {
      title: "The quest: the job interview",
      intro: "You are having a job interview. 4 challenges: listening, reading, writing, speaking. Pass them to earn your badge.",
      start: "Start the quest", next: "Continue", again: "Play again",
      step: "Challenge", of: "of",
      listen: "Listen", read: "Read", write: "Write", speak: "Speak",
      play: "▶ Listen to the question", replay: "▶ Listen again",
      noTTS: "Your browser cannot read English aloud. Read the text below.",
      transcript: "Text:",
      correct: "Well done!", wrong: "Not quite. The right answer is in green.",
      checkBtn: "Check", writeHint: "Write 2 sentences in English: your name, your job or studies, and why you want this job.",
      c_len: "At least 8 words", c_intro: "You introduce yourself (I am / My name is / I'm)",
      c_why: "You give a reason (because / want / would like)", c_end: "You end with a full stop",
      note: "Prototype: this check is simple. Detailed AI feedback comes in the next version.",
      speakHint: "Tap the microphone and say the sentence aloud, in English.",
      mic: "🎤 Speak", listening: "🎤 Listening…",
      heard: "I heard:", match: "Match:",
      noSR: "Speech recognition is not available in this browser (try Chrome). Say the sentence aloud, then rate yourself:",
      selfOk: "I said it correctly", selfKo: "I need to practise",
      done: "Quest complete!", total: "Total score", badge: "Badge earned: Interview-ready candidate",
      level: "Target level: A2 to B1", pts: "points",
      streakMsg: "Current streak (days):",
      micDenied: "Microphone denied or unavailable. Allow it, or rate yourself."
    }
  };

  /* ---------- Contenu de la quête (anglais) ---------- */
  var QUEST = [
    { type: "listen",
      say: "Hello, I am Sarah, the manager. Please tell me about yourself.",
      q: { fr: "Que demande Sarah ?", ar: "ماذا تطلب سارة؟", en: "What does Sarah ask?" },
      opts: [
        { en: "She asks you to talk about yourself.", ok: true },
        { en: "She asks you to give her your address." },
        { en: "She asks you to sign a contract." }
      ] },
    { type: "read",
      text: "Hi, thank you for your application. The interview is on Monday at 10 a.m. Please bring your CV and your ID card.",
      qs: [
        { q: { fr: "Quand est l'entretien ?", ar: "متى المقابلة؟", en: "When is the interview?" },
          opts: [{ en: "On Monday at 10 a.m.", ok: true }, { en: "On Tuesday at 10 a.m." }, { en: "On Monday at 2 p.m." }] },
        { q: { fr: "Que faut-il apporter ?", ar: "ماذا يجب أن تحضر؟", en: "What must you bring?" },
          opts: [{ en: "A photo and a diploma" }, { en: "Your CV and your ID card", ok: true }, { en: "A gift for the manager" }] }
      ] },
    { type: "write" },
    { type: "speak", say: "I would like to work in your company because I like teamwork." }
  ];

  /* ---------- État et sauvegarde locale ---------- */
  var KEY = "englishQuest.v1";
  var S = { lang: "fr", xp: 0, streak: 0, lastDay: "" };
  try { var saved = JSON.parse(localStorage.getItem(KEY) || "{}"); for (var k in saved) S[k] = saved[k]; } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }

  var run = { step: -1, scores: [0, 0, 0, 0] };
  var $ = function (id) { return document.getElementById(id); };
  var t = function (key) { return (T[S.lang] && T[S.lang][key]) || T.en[key] || key; };

  function dayKey(d) { return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate(); }
  function updateStreak() {
    var now = new Date(), today = dayKey(now);
    if (S.lastDay === today) return;
    var y = new Date(now); y.setDate(now.getDate() - 1);
    S.streak = (S.lastDay === dayKey(y)) ? S.streak + 1 : 1;
    S.lastDay = today; save();
  }

  /* ---------- Voix (écouter) ---------- */
  function speak(text) {
    if (!("speechSynthesis" in window)) return false;
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US"; u.rate = 0.9;
    window.speechSynthesis.speak(u);
    return true;
  }

  /* ---------- Rendu ---------- */
  function setLang(l) {
    S.lang = l; save();
    document.documentElement.lang = l;
    document.documentElement.dir = (l === "ar") ? "rtl" : "ltr";
    var bs = document.querySelectorAll(".lang");
    for (var i = 0; i < bs.length; i++) bs[i].classList.toggle("on", bs[i].getAttribute("data-lang") === l);
    render();
  }
  function head() {
    $("streak").textContent = S.streak; $("xp").textContent = S.xp;
    $("bar").style.width = (run.step < 0 ? 0 : Math.min(100, (run.step / 4) * 100)) + "%";
  }
  function el(html) { $("screen").innerHTML = html; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function render() {
    head();
    if (run.step < 0) return home();
    if (run.step >= 4) return finish();
    var s = QUEST[run.step];
    if (s.type === "listen") return viewListen(s);
    if (s.type === "read") return viewRead(s);
    if (s.type === "write") return viewWrite();
    return viewSpeak(s);
  }
  function stepTitle(key) {
    return "<p class='muted'>" + t("step") + " " + (run.step + 1) + " " + t("of") + " 4 — " + t(key) + "</p>";
  }

  function home() {
    el("<div class='card'><div class='big'>🎯</div><h1>" + esc(t("title")) + "</h1><p>" + esc(t("intro")) + "</p>" +
       "<p class='muted'>" + t("streakMsg") + " " + S.streak + "</p>" +
       "<button class='btn' id='go'>" + t("start") + "</button></div>");
    $("go").onclick = function () { run = { step: 0, scores: [0, 0, 0, 0] }; render(); };
  }

  /* Question à choix : renvoie 1 si juste, 0 sinon */
  function mcq(container, opts, onDone) {
    var order = opts.map(function (o, i) { return i; });
    order.sort(function () { return Math.random() - 0.5; });
    var html = "";
    order.forEach(function (i) { html += "<button class='opt en' data-i='" + i + "'>" + esc(opts[i].en) + "</button>"; });
    container.innerHTML = html;
    var done = false;
    container.querySelectorAll(".opt").forEach(function (b) {
      b.onclick = function () {
        if (done) return; done = true;
        var i = +b.getAttribute("data-i"), good = !!opts[i].ok;
        b.classList.add(good ? "good" : "bad");
        if (!good) container.querySelectorAll(".opt").forEach(function (x) { if (opts[+x.getAttribute("data-i")].ok) x.classList.add("good"); });
        onDone(good ? 1 : 0);
      };
    });
  }
  function nextBtn(box) {
    var b = document.createElement("button");
    b.className = "btn"; b.textContent = t("next");
    b.onclick = function () { run.step++; render(); };
    box.appendChild(b);
  }

  function viewListen(s) {
    el("<div class='card'>" + stepTitle("listen") + "<button class='btn sec' id='play'>" + t("play") + "</button>" +
       "<p class='muted' id='tts' style='display:none'></p><h2>" + esc(s.q[S.lang]) + "</h2><div id='opts'></div><div id='fb'></div></div>");
    $("play").onclick = function () {
      var ok = speak(s.say);
      $("play").textContent = t("replay");
      if (!ok) { $("tts").style.display = "block"; $("tts").innerHTML = esc(t("noTTS")) + "<div class='say'>" + esc(s.say) + "</div>"; }
    };
    mcq($("opts"), s.opts, function (g) {
      run.scores[0] = g * 25;
      $("fb").innerHTML = "<p class='" + (g ? "ok" : "ko") + "'>" + t(g ? "correct" : "wrong") + "</p>" +
        "<p class='muted'>" + t("transcript") + "</p><div class='say'>" + esc(s.say) + "</div>";
      nextBtn($("fb"));
    });
  }

  function viewRead(s) {
    var i = 0, good = 0;
    el("<div class='card'>" + stepTitle("read") + "<div class='say' style='font-weight:500'>" + esc(s.text) + "</div>" +
       "<h2 id='q'></h2><div id='opts'></div><div id='fb'></div></div>");
    function ask() {
      var cur = s.qs[i];
      $("q").textContent = cur.q[S.lang]; $("fb").innerHTML = "";
      mcq($("opts"), cur.opts, function (g) {
        good += g; i++;
        $("fb").innerHTML = "<p class='" + (g ? "ok" : "ko") + "'>" + t(g ? "correct" : "wrong") + "</p>";
        var b = document.createElement("button"); b.className = "btn"; b.textContent = t("next");
        b.onclick = function () {
          if (i < s.qs.length) ask();
          else { run.scores[1] = Math.round(good / s.qs.length * 25); run.step++; render(); }
        };
        $("fb").appendChild(b);
      });
    }
    ask();
  }

  function viewWrite() {
    el("<div class='card'>" + stepTitle("write") + "<p>" + esc(t("writeHint")) + "</p>" +
       "<textarea id='ta' class='en' dir='ltr' placeholder='My name is ... I am ... I would like this job because ...'></textarea>" +
       "<button class='btn' id='chk'>" + t("checkBtn") + "</button><div id='fb'></div></div>");
    $("chk").onclick = function () {
      var txt = $("ta").value.trim();
      var words = txt.split(/\s+/).filter(Boolean).length;
      var c = [
        ["c_len", words >= 8],
        ["c_intro", /\b(i am|i'm|my name is)\b/i.test(txt)],
        ["c_why", /\b(because|want|would like|like to)\b/i.test(txt)],
        ["c_end", /[.!?]\s*$/.test(txt)]
      ];
      var n = c.filter(function (x) { return x[1]; }).length;
      run.scores[2] = Math.round(n / 4 * 25);
      var li = c.map(function (x) { return "<li class='" + (x[1] ? "ok" : "ko") + "'>" + (x[1] ? "✔ " : "✘ ") + esc(t(x[0])) + "</li>"; }).join("");
      $("chk").disabled = true; $("ta").disabled = true;
      $("fb").innerHTML = "<ul class='check'>" + li + "</ul><p class='muted'>" + esc(t("note")) + "</p>";
      nextBtn($("fb"));
    };
  }

  function norm(s) { return s.toLowerCase().replace(/[^a-z0-9' ]/g, " ").split(/\s+/).filter(Boolean); }
  function similarity(a, b) {
    var A = norm(a), B = norm(b); if (!B.length) return 0;
    var hit = 0; B.forEach(function (w) { if (A.indexOf(w) !== -1) hit++; });
    return hit / B.length;
  }

  function viewSpeak(s) {
    el("<div class='card'>" + stepTitle("speak") + "<p>" + esc(t("speakHint")) + "</p><div class='say'>" + esc(s.say) + "</div>" +
       "<button class='btn sec' id='hear'>" + t("play") + "</button><button class='btn' id='mic'>" + t("mic") + "</button><div id='fb'></div></div>");
    $("hear").onclick = function () { speak(s.say); };
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    function selfRate(msg) {
      $("fb").innerHTML = "<p class='muted'>" + esc(msg) + "</p><div class='row'><button class='btn' id='y'>" + t("selfOk") +
        "</button><button class='btn sec' id='n'>" + t("selfKo") + "</button></div>";
      $("y").onclick = function () { run.scores[3] = 25; run.step++; render(); };
      $("n").onclick = function () { run.scores[3] = 10; run.step++; render(); };
    }
    if (!SR) { $("mic").style.display = "none"; return selfRate(t("noSR")); }
    $("mic").onclick = function () {
      var r = new SR(); r.lang = "en-US"; r.interimResults = false; r.maxAlternatives = 1;
      $("mic").textContent = t("listening"); $("mic").disabled = true;
      r.onresult = function (e) {
        var heard = e.results[0][0].transcript, sim = similarity(heard, s.say);
        run.scores[3] = Math.round(sim * 25);
        $("fb").innerHTML = "<p class='muted'>" + t("heard") + "</p><div class='say'>" + esc(heard) + "</div><p class='" + (sim >= 0.7 ? "ok" : "ko") +
          "'>" + t("match") + " " + Math.round(sim * 100) + " %</p>";
        $("mic").style.display = "none"; nextBtn($("fb"));
      };
      r.onerror = function () { $("mic").style.display = "none"; selfRate(t("micDenied")); };
      r.onend = function () { if (!$("fb").innerHTML) { $("mic").textContent = t("mic"); $("mic").disabled = false; } };
      try { r.start(); } catch (err) { selfRate(t("micDenied")); }
    };
  }

  function finish() {
    var total = run.scores.reduce(function (a, b) { return a + b; }, 0);
    S.xp += total; updateStreak(); save(); head();
    $("bar").style.width = "100%";
    var names = ["listen", "read", "write", "speak"];
    var rows = names.map(function (k, i) { return "<li>" + t(k) + " : <b>" + run.scores[i] + "/25</b></li>"; }).join("");
    el("<div class='card'><div class='big'>🏆</div><h1>" + t("done") + "</h1><div class='score'>" + total + "/100</div>" +
       "<ul class='check'>" + rows + "</ul><p class='ok'>" + t("badge") + "</p><p class='muted'>" + t("level") + "</p>" +
       "<p class='muted'>" + t("streakMsg") + " " + S.streak + "</p><button class='btn' id='again'>" + t("again") + "</button></div>");
    $("again").onclick = function () { run = { step: -1, scores: [0, 0, 0, 0] }; render(); };
  }

  /* ---------- Démarrage ---------- */
  document.querySelectorAll(".lang").forEach(function (b) {
    b.onclick = function () { setLang(b.getAttribute("data-lang")); };
  });
  setLang(S.lang);
})();

"use client";

import { useState } from "react";
import type { QuizQuestion, QuizState, QuizSubmitResponse } from "@/lib/types";
import { chat } from "@/lib/api";

interface QuizArtifactProps {
  title: string;
  content: string;
  metadata?: Record<string, unknown>;
  sessionId?: number;
}

export function QuizArtifact({ title, content, metadata, sessionId }: QuizArtifactProps) {
  const [quizState, setQuizState] = useState<QuizState>(() => {
    let questions: QuizQuestion[] = [];
    try {
      questions = JSON.parse(content);
    } catch {
      // try to parse markdown
      questions = [];
    }
    return {
      questions,
      answers: new Array(questions.length).fill(null),
      score: null,
      submitted: false,
    };
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<QuizSubmitResponse | null>(null);

  const handleSelect = (qIndex: number, oIndex: number) => {
    if (quizState.submitted) return;
    setQuizState((prev) => {
      const answers = [...prev.answers];
      answers[qIndex] = oIndex;
      return { ...prev, answers };
    });
  };

  const handleSubmit = async () => {
    const correct = quizState.questions.reduce((sum, q, i) => {
      return sum + (q.correct_index === quizState.answers[i] ? 1 : 0);
    }, 0);
    setQuizState((prev) => ({
      ...prev,
      submitted: true,
      score: correct,
    }));

    // Correctif 2 : envoyer le score au backend pour mettre à jour la maîtrise Leitner
    setSubmitting(true);
    try {
      const result = await chat.submitQuiz({
        session_id: sessionId,
        competency_id: (metadata?.competency_id as number) ?? undefined,
        competency_name: (metadata?.competency_name as string) ?? undefined,
        correct,
        total: quizState.questions.length,
      });
      setSubmitResult(result);
    } catch (err) {
      console.error("Quiz submit error:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const allAnswered = quizState.answers.every((a) => a !== null);

  return (
    <div className="rounded-xl border border-zinc-800 bg-surface-1 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-surface-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-emerald-400 font-medium">Quiz</span>
          <span className="text-xs text-zinc-500">{title}</span>
        </div>
        {quizState.submitted && quizState.score !== null && (
          <span className="text-xs font-medium text-emerald-400">
            {quizState.score}/{quizState.questions.length}
          </span>
        )}
      </div>

      <div className="p-4 space-y-4">
        {quizState.questions.map((q, qi) => (
          <div key={qi} className="space-y-2">
            <p className="text-sm text-zinc-200">
              <span className="font-medium text-zinc-400">{qi + 1}.</span> {q.question}
            </p>
            <div className="space-y-1.5 pl-4">
              {q.options.map((opt, oi) => {
                const isSelected = quizState.answers[qi] === oi;
                const isCorrect = q.correct_index === oi;
                const showResult = quizState.submitted;

                let borderColor = "border-zinc-700";
                let bgColor = "bg-surface-2";
                let textColor = "text-zinc-300";

                if (showResult && isCorrect) {
                  borderColor = "border-emerald-500";
                  bgColor = "bg-emerald-500/10";
                  textColor = "text-emerald-400";
                } else if (showResult && isSelected && !isCorrect) {
                  borderColor = "border-red-500";
                  bgColor = "bg-red-500/10";
                  textColor = "text-red-400";
                } else if (isSelected) {
                  borderColor = "border-primary-500";
                  bgColor = "bg-primary-500/10";
                  textColor = "text-primary-400";
                }

                return (
                  <button
                    key={oi}
                    onClick={() => handleSelect(qi, oi)}
                    disabled={quizState.submitted}
                    className={`w-full text-left px-3 py-2 rounded-lg border ${borderColor} ${bgColor} ${textColor} text-sm transition-colors disabled:cursor-default`}
                  >
                    <span className="font-mono text-xs mr-2 opacity-50">
                      {String.fromCharCode(65 + oi)}
                    </span>
                    {opt}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        {!quizState.submitted && allAnswered && (
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {submitting ? "Envoi..." : "Valider"}
          </button>
        )}

        {quizState.submitted && (
          <div className="text-center py-2 space-y-2">
            <div className="text-sm text-zinc-400">
              Score : <span className="text-emerald-400 font-bold">{quizState.score}</span> / {quizState.questions.length}
            </div>
            {/* Correctif 2 : feedback + maîtrise renvoyés par le backend */}
            {submitResult && (
              <div className="text-xs text-zinc-500 space-y-1">
                <p className="text-zinc-300">{submitResult.feedback}</p>
                {submitResult.mastery && (
                  <p>
                    Maîtrise : <span className="text-primary-400 font-medium">{Math.round(submitResult.mastery.score * 100)}%</span>
                    {" · "}boîte Leitner {submitResult.mastery.leitner_box}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

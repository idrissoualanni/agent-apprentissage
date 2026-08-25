"use client";

import { useState } from "react";
import type { QuizQuestion, QuizState } from "@/lib/types";

interface QuizArtifactProps {
  title: string;
  content: string;
}

export function QuizArtifact({ title, content }: QuizArtifactProps) {
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

  const handleSelect = (qIndex: number, oIndex: number) => {
    if (quizState.submitted) return;
    setQuizState((prev) => {
      const answers = [...prev.answers];
      answers[qIndex] = oIndex;
      return { ...prev, answers };
    });
  };

  const handleSubmit = () => {
    const correct = quizState.questions.reduce((sum, q, i) => {
      return sum + (q.correct_index === quizState.answers[i] ? 1 : 0);
    }, 0);
    setQuizState((prev) => ({
      ...prev,
      submitted: true,
      score: correct,
    }));
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
            className="w-full py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Valider
          </button>
        )}

        {quizState.submitted && (
          <div className="text-center py-2 text-sm text-zinc-400">
            Score : <span className="text-emerald-400 font-bold">{quizState.score}</span> / {quizState.questions.length}
          </div>
        )}
      </div>
    </div>
  );
}

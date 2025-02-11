import { Card, CardContent } from "@/components/ui/card";
import { BookOpen } from "lucide-react";

const Abstract = () => {
  return (
    <section className="py-6 fade-in">
      <div className="max-w-3xl mx-auto px-4">
        <div className="flex items-center gap-3 mb-6">
          <BookOpen className="h-6 w-6 text-primary" />
          <h2 className="text-3xl font-bold">Abstract</h2>
        </div>
        <Card className="hover:shadow-xl transition-all duration-300">
          <CardContent className="p-8 prose prose-gray">
            <p className="text-lg leading-relaxed text-muted-foreground">
              The use of LLMs as automated judges ("LLM-as-a-judge") is now
              widespread, yet existing approaches suffer from a multitude of
              reliability issues. To address these challenges, we introduce
              Verdict, an open-source library for constructing compound LLM
              judge architectures that enhance the accuracy, reliability, and
              interpretability of automated evaluations. Verdict leverages the
              composition of modular reasoning units &mdash; such as verification,
              debate, and aggregation &mdash; and increased inference-time compute to
              improve evaluation quality. Across a variety of challenging tasks
              such as content moderation, factual correctness, and hallucination
              detection, <strong>Verdict judges achieve state-of-the-art (SOTA) or
              near-SOTA performance</strong>, surpassing orders-of-magnitude larger
              fine-tuned judges, prompted judges, and reasoning models.
              Ultimately, we hope Verdict serves as a useful framework for
              researchers and practitioners building scalable, interpretable,
              and reliable LLM-based evaluators.
            </p>
          </CardContent>
        </Card>
      </div>
    </section>
  );
};

export default Abstract;

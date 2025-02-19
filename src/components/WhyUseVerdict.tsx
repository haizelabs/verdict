
import { Card, CardContent } from "@/components/ui/card";
import { Target } from "lucide-react";

const reasons = [
  {
    title: "Reliability",
    description:
      "Verdict judges are stable, accurate, and reliable. Verdict judges beat out single-inference LLM judges, fine-tuned evaluators, and even o1-style reasoning models on a wide range of evaluation benchmarks.",
  },
  {
    title: "Generalizability",
    description:
      "Verdict judges are general-purpose evaluators. Verdict readily applies across different tasks and domains, as seen by the above experiments on content moderation, factual and logical correctness, and hallucination detection.",
  },
  {
    title: "Saliency",
    description:
      "Verdict judges generate rich rewards even in non-verifiable settings, enabling reasoning model progress beyond the current frontiers of mathematics and programming."
  },
  {
    title: "Efficiency",
    description:
      "Verdict judges are just as powerful as –– if not more powerful than –– o1-style models at evaluation, while incurring only a fraction of the latency and cost.",
  },
];

const WhyUseVerdict = () => {
  return (
    <section className="py-16 fade-in">
      <div className="max-w-5xl mx-auto px-4">
        <div className="flex items-center gap-3 mb-8">
          <Target className="h-8 w-8 text-primary" />
          <h2 className="text-3xl font-bold">Why Use Verdict?</h2>
        </div>
        <div className="space-y-6">
          {reasons.map((reason, index) => (
            <Card
              key={index}
              className="group border-none hover:bg-white/40 transition-all duration-200 bg-white/80 backdrop-blur-sm"
            >
              <CardContent className="flex items-start gap-4 p-6">
                <span className="text-2xl font-bold text-primary/70">{index + 1}.</span>
                <div>
                  <h3 className="text-xl font-semibold mb-2">{reason.title}</h3>
                  <p className="text-muted-foreground">{reason.description}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default WhyUseVerdict;

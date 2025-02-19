
import { Card, CardContent } from "@/components/ui/card";
import { Target } from "lucide-react";

const reasons = [
  {
    title: "Generalizability",
    description:
      "Verdict judges are more general than task-specific fine-tuned models. Verdict readily applies across different tasks and domains, as seen by our experiments on safety moderation, factual and logical correctness, and hallucination detection.",
  },
  {
    title: "Reliability",
    description:
      "Verdict judges are more stable, accurate, and reliable compared to simple LLM judges. Verdict judges beat out simple LLM judges, fine-tuned evaluators, and even o1-style reasoning models on our benchmarks.",
  },
  {
    title: "Saliency",
    description:
      "Verdict judges are capable of generating dense partial rewards, unlike (non-ML) verifiers in settings like mathematics or programming.",
  },
  {
    title: "Efficiency",
    description:
      "Verdict judges are just as powerful as –– if not more powerful than –– o1-style models at evaluation while being much lower-latency and cost-efficient. This is necessary for any method leveraging heavy inference-time compute.",
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

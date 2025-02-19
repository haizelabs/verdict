
import { Scale, Shield, ChartLine, Brain } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

const applications = [
  {
    icon: <Scale className="h-7 w-7" />,
    title: "Automated Evaluation of AI Applications",
    description: "Verdict judges enable tailored and automated evaluation of AI applications.",
  },
  {
    icon: <Shield className="h-7 w-7" />,
    title: "Run-Time Guardrails",
    description: "Verdict judges are guardrails that sit on top of AI applications running in production.",
  },
  {
    icon: <ChartLine className="h-7 w-7" />,
    title: "Test-Time Compute Scaling",
    description: "Verdict judges are verifiers that help rank, prune, and select candidates during test-time compute scaling.",
  },
  {
    icon: <Brain className="h-7 w-7" />,
    title: "Reward Modeling & Reinforcement Learning",
    description: "Verdict judges provide signal in reinforcement learning — particularly in settings where rewards are not verifiable.",
  },
];

const Applications = () => {
  return (
    <section className="py-16 fade-in">
      <div className="max-w-5xl mx-auto px-4">
        <div className="flex items-center gap-3 mb-8">
          <Scale className="h-8 w-8 text-primary" />
          <h2 className="text-3xl font-bold">Verdict Applications</h2>
        </div>
        <p className="text-lg text-muted-foreground mb-12 max-w-3xl">
          Verdict judges can be used anywhere to replace human feedback and verification. 
          Naturally, they can be used for evaluation, guardrails, test-time verification, 
          and Reinforcement Learning.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-8">
          {applications.map((app, index) => (
            <Card 
              key={index} 
              className="group border-none hover:bg-white/40 transition-all duration-200 bg-white/80 backdrop-blur-sm"
            >
              <CardContent className="flex items-start gap-4 p-6">
                <div className="p-2 bg-primary/[0.03] rounded-lg group-hover:bg-primary/[0.08] transition-colors duration-300">
                  <div className="text-primary">{app.icon}</div>
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-2">{app.title}</h3>
                  <p className="text-muted-foreground">{app.description}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Applications;

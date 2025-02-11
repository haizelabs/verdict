import { Card, CardContent } from "@/components/ui/card";
import {
  Database,
  ChartBar,
  ToyBrick,
  Code,
  Puzzle,
  Zap,
  Shield,
  Share2,
} from "lucide-react";

const features = [
  {
    icon: <Code className="h-6 w-6" />,
    title: "Unified Interface",
    description:
      "Verdict provides a single interface for evaluation protocols inspired by scalable oversight, auto-evaluation, reward modeling, and more.",
  },
  {
    icon: <Puzzle className="h-6 w-6" />,
    title: "Composable & Expressive",
    description:
      "Verdict systems are arbitrarily composable, allowing one to create rich and expressive, yet stable judging architectures.",
  },
  {
    icon: <ToyBrick className="h-6 w-6" />,
    title: "Powerful Primitives",
    description:
      "Verdict introduces powerful automated evaluation patterns, such as hierarchical reasoning verification and debate-aggregation",
  },
];

const Features = () => {
  return (
    <section className="py-16">
      <div className="max-w-6xl mx-auto px-4">
        <h2 className="text-3xl font-bold text-center mb-12">
          Verdict Core Features
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, index) => (
            <Card
              key={index}
              className="border-none hover:shadow-xl transition-all duration-300 hover:-translate-y-1"
            >
              <CardContent className="p-6">
                <div className="mb-4 inline-block p-3 bg-primary/10 rounded-full">
                  <div className="text-primary">{feature.icon}</div>
                </div>
                <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
                <p className="text-muted-foreground">{feature.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Features;

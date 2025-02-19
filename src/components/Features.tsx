
import { Card, CardContent } from "@/components/ui/card";
import {
  Code,
  Puzzle,
  Blocks,
} from "lucide-react";

const features = [
  {
    icon: <Code className="h-7 w-7" />,
    title: "Unified Interface",
    description:
      "Verdict provides a single interface for evaluation protocols inspired by scalable oversight, auto-evaluation, reward modeling, and more.",
    link: "https://verdict.haizelabs.com/docs/concept/overview/",
  },
  {
    icon: <Blocks className="h-7 w-7" />,
    title: "Composable & Expressive",
    description:
      "Create rich and expressive, yet stable judging architectures with Verdict's composable evaluation systems.",
    link: "https://verdict.haizelabs.com/docs/concept/layer/",
  },
  {
    icon: <Puzzle className="h-7 w-7" />,
    title: "Powerful Primitives",
    description:
      "Verdict introduces powerful automated evaluation patterns, such as hierarchical reasoning verification and debate-aggregation",
    link: "https://verdict.haizelabs.com/docs/concept/unit/",
  },
];

const Features = () => {
  return (
    <section className="py-16">
      <div className="max-w-5xl mx-auto px-4">
        <h2 className="text-3xl font-bold text-center mb-12">
          Verdict Core Features
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <a 
              key={index}
              href={feature.link}
              target="_blank"
              rel="noopener noreferrer"
              className="block no-underline h-full"
            >
              <Card
                className="group border-none hover:shadow-xl transition-all duration-300 hover:-translate-y-2 bg-white/80 backdrop-blur-sm h-full"
              >
                <CardContent className="p-8">
                  <div className="mb-6 inline-block p-4 bg-primary/[0.03] rounded-lg group-hover:bg-primary/[0.08] transition-colors duration-300 relative">
                    <div className="absolute inset-0 bg-primary/[0.03] rounded-lg transform rotate-6 transition-transform group-hover:rotate-12"></div>
                    <div className="relative">
                      <div className="text-primary transform transition-transform duration-300 group-hover:scale-110">
                        {feature.icon}
                      </div>
                    </div>
                  </div>
                  <h3 className="text-xl font-semibold mb-3">{feature.title}</h3>
                  <p className="text-muted-foreground leading-relaxed">{feature.description}</p>
                </CardContent>
              </Card>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Features;

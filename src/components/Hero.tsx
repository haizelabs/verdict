import { Github, BookOpen, BookText, Users, Rocket, Star, Quote } from "lucide-react";
import { Button } from "@/components/ui/button";
import MetricCard from "./MetricCard";

const Hero = () => {
  return (
    <div className="py-20 space-y-12">
      <div className="space-y-6 text-center max-w-6xl mx-auto px-4 fade-in">
        <div className="flex flex-col items-center space-x-4">
          <img
            src={"../../hero-transparent.png"}
            alt="Verdict logo with an example Verdict pipeline diagram in the background"
            className="h-auto w-5/6"
          />
        </div>
        <div className="space-y-1">
          <div className="text-xl tracking-tight text-foreground">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-3xl bg-clip-text pb-2">
              A Library for Compound LLM Judge Systems
            </h1>
            <span className="font-semibold">
              <a href="https://nimit.io" class="font-medium text-blue-600 dark:text-blue-500 hover:underline">Nimit Kalra</a>
            </span>{" "}·{" "}
            <span className="font-semibold">
              <a href="https://leonardtang.me/tabs/about" class="font-medium text-blue-600 dark:text-blue-500 hover:underline">Leonard Tang</a>
            </span>
          </div>
          <div className="text-xl tracking-wide uppercase font-medium text-muted-foreground">
            <span><a href="https://haizelabs.com" class="font-small text-blue-600 dark:text-blue-500 hover:underline">Haize Labs</a></span>
          </div>
          <div className="text-sm tracking-wide uppercase text-muted-foreground">
            New York City
          </div>
        </div>
      </div>

      <div className="flex flex-wrap justify-center gap-4 fade-in">
        <a href="https://github.com/haizelabs/verdict">
          <Button variant="default" className="gap-2 w-40 shadow-lg hover:shadow-xl transition-all font-medium">
            <Github className="h-4 w-4" />
            View on GitHub
          </Button>
        </a>

        <a href="https://verdict.haizelabs.com/whitepaper.pdf" target="_blank">
          <Button variant="outline" className="gap-2 w-40 shadow hover:shadow-lg transition-all font-medium">
            <BookOpen className="h-4 w-4" />
            Read Paper
          </Button>
        </a>

        <a href="https://verdict.haizelabs.com/docs">
          <Button variant="default" className="gap-2 w-40 shadow-lg hover:shadow-xl transition-all font-medium">
            <BookText className="h-4 w-4" />
            Read the Docs
          </Button>
        </a>
      </div>

      {/* <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl mx-auto px-4 fade-in">
        <MetricCard
          icon={<Star className="h-5 w-5" />}
          label="GitHub Stars"
          value="1.2k"
        />
        <MetricCard
          icon={<Quote className="h-5 w-5" />}
          label="Citations"
          value="45"
        />
        <MetricCard
          icon={<Users className="h-5 w-5" />}
          label="Contributors"
          value="23"
        />
      </div> */}
    </div>
  );
};

export default Hero;

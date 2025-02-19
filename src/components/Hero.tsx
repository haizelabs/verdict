
import { Github, BookOpen, BookText } from "lucide-react";
import { Button } from "@/components/ui/button";

const Hero = () => {
  return (
    <div className="py-20 space-y-16">
      <div className="space-y-8 text-center max-w-6xl mx-auto px-4 fade-in">
        <div className="flex flex-col items-center">
          <img
            src={"../../hero-transparent.png"}
            alt="Verdict logo with an example Verdict pipeline diagram in the background"
            className="h-auto w-5/6 opacity-90 mb-8"
          />
        </div>
        <div className="space-y-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-wider sm:text-3xl bg-clip-text letter-spacing-2">
              Verdict: A Library for Scaling Judge-Time Compute
            </h1>
          </div>
          <div className="text-2xl tracking-wide uppercase font-medium text-muted-foreground pt-2">
            <div>
              <a href="https://haizelabs.com" target="_blank" className="font-semibold text-primary underline hover:text-red-800 decoration-[3px] underline-offset-4 tracking-widest">Haize Labs</a>
            </div>
          </div>
          <div className="text-base tracking-wide text-muted-foreground mt-6">
            <div className="space-x-6 flex flex-row justify-center font-semibold mb-4">
              <div>
                <a href="https://nimit.io" target="_blank" className="hover:text-red-800 underline decoration-[2px] underline-offset-4 tracking-normal">Nimit Kalra</a>
                {" "}&bull;{" "}
                <a href="https://leonardtang.me/tabs/about" target="_blank" className="hover:text-red-800 underline decoration-[2px] underline-offset-4 tracking-normal">Leonard Tang</a>
              </div>
            </div>
            <div className="tracking-normal text-black">
              ——— Made in NYC ———
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap justify-center gap-4 fade-in">
        <a href="https://github.com/haizelabs/verdict">
          <Button variant="outline" className="button-retro w-40 font-medium">
            <Github className="h-4 w-4" />
            GitHub
          </Button>
        </a>

        <a href="https://verdict.haizelabs.com/whitepaper.pdf" target="_blank">
          <Button variant="outline" className="button-retro w-40 font-medium">
            <BookOpen className="h-4 w-4" />
            Paper
          </Button>
        </a>

        <a href="https://verdict.haizelabs.com/docs">
          <Button variant="outline" className="button-retro w-40 font-medium">
            <BookText className="h-4 w-4" />
            Docs
          </Button>
        </a>
      </div>
    </div>
  );
};

export default Hero;

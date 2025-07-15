import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Terminal, Code2, Rocket } from "lucide-react";
import { useToast } from "@/components/ui/use-toast";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { FiClipboard } from "react-icons/fi";
import { vs } from "react-syntax-highlighter/dist/esm/styles/prism";

const InstallationGuide = () => {
  const { toast } = useToast();
  const [isRendering, setIsRendering] = useState(true);

  useEffect(() => {
    // Wait until all syntax highlighting is applied
    const timeout = setTimeout(() => setIsRendering(false), 700); // Adjust timing if needed
    return () => clearTimeout(timeout);
  }, []);

  const handleCopy = (content) => {
    navigator.clipboard.writeText(content);
    toast({
      title: "Copied to clipboard",
      description: "The command has been copied to your clipboard.",
      duration: 1000,
    });
  };

  const SyntaxHighlightedContent = ({
    language,
    content,
  }: {
    language: string;
    content: string;
  }) => {
    return (
      <div className="syntax-highlighter-container relative group">
        <SyntaxHighlighter
          language={language}
          style={vs}
          customStyle={{
            borderRadius: "0.5rem",
            padding: "1rem",
            backgroundColor: "hsl(220, 10%, 98%)",
          }}
        >
          {content}
        </SyntaxHighlighter>
        <button
          onClick={() => handleCopy(content)}
          className="absolute top-4 right-4 p-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200
            border border-primary hover:bg-primary/10 rounded"
        >
          <FiClipboard className="w-4 h-4 text-primary" />
        </button>
      </div>
    );
  };

  const installation = `# using pip...
pip install verdict

# or using uv
conda create -n verdict python=3.13 # we support python >= 3.9
conda activate verdict
uv pip install verdict`;

  const prereqs = `# log into HF for dataset access...
huggingface-cli login
  
# set API key
export OPENAI_API_KEY=XXXXXXXXXXXXXXXXX`

  const code = `# quickstart.py
from verdict import Pipeline
from verdict.common.judge import PairwiseJudgeUnit
from verdict.dataset import DatasetWrapper
from verdict.schema import Schema
from verdict.extractor import ArgmaxScoreExtractor
from datasets import load_dataset

### (Optional) Disable client-side rate-limiting ###
# from verdict.util import ratelimit
# ratelimit.disable()

### Load the JudgeBench dataset from HuggingFace ###
dataset = DatasetWrapper.from_hf(
    load_dataset("ScalerLab/JudgeBench"),
    columns=["question", "response_A", "response_B"],
    max_samples=10
)

### Define a Verdict pipeline ###
pipeline = Pipeline("Pairwise") \\
  >> PairwiseJudgeUnit().prompt("""
      Determine which response is preferable.

      ## Prompt:
      {source.question}

      ## Response A:
      {source.response_A}

      ## Response B:
      {source.response_B}

      Respond with only "A" or "B".
  """).extract(ArgmaxScoreExtractor()) \\
      .via("gpt-4o-mini", retries=3, temperature=0.0)

### Execute the pipeline over the dataset in parallel ###
df, _ = pipeline.run_from_dataset(dataset["claude"], display=True)
print(df)
`;

  const execute = `python quickstart.py`;

  return (
    <section className="py-6 fade-in overflow-hidden">
      <div className="mx-auto px-4 sm:px-6">
        {isRendering ? (
          <div className="flex justify-center items-center h-32">
            <p className="text-primary">Loading...</p>
          </div>
        ) : (
          <div className="space-y-6 sm:space-y-8">
            <Card className="hover:shadow-xl transition-all duration-300 bg-popover w-full max-w-full">
              <CardContent className="p-4 sm:p-6 w-full">
                <div className="flex flex-wrap items-center gap-2 mb-3 sm:mb-4">
                  <Terminal className="h-5 w-5 text-primary" />
                  <h3 className="text-lg sm:text-xl font-semibold">
                    Installation
                  </h3>
                </div>
                <SyntaxHighlightedContent language="python" content={installation} />
              </CardContent>
            </Card>

            <Card className="hover:shadow-xl transition-all duration-300 bg-popover w-full max-w-full">
              <CardContent className="p-4 sm:p-6 w-full">
                <div className="flex flex-wrap items-center gap-2 mb-3 sm:mb-4">
                  <Rocket className="h-5 w-5 text-primary" />
                  <h3 className="text-lg sm:text-xl font-semibold">Quickstart</h3>
                </div>
                <SyntaxHighlightedContent language="python" content={prereqs} />
                <SyntaxHighlightedContent language="python" content={code} />
                <SyntaxHighlightedContent language="python" content={execute} />
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </section>
  );
};

export default InstallationGuide;

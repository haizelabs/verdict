
import { Card, CardContent } from "@/components/ui/card";
import { Terminal, Code2, Rocket } from "lucide-react";
import { useToast } from "@/components/ui/use-toast";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { FiClipboard } from "react-icons/fi";
import { vs } from "react-syntax-highlighter/dist/esm/styles/prism";

const InstallationGuide = () => {
  const { toast } = useToast();
  const handleCopy = (content) => {
    navigator.clipboard.writeText(content);
    toast({
      title: "Copied to clipboard",
      description: "The command has been copied to your clipboard.",
      duration: 1000,
    });
  };

  // Customize the VS theme with retro-inspired colors
  const customStyle = {
    ...vs,
    'code[class*="language-"]': {
      ...vs['code[class*="language-"]'],
      background: 'hsl(220, 10%, 98%)', // Much more muted, almost white background
      color: 'hsl(220, 25%, 25%)', // Darker text for better contrast
      fontSize: '0.9rem', // Slightly smaller font size
      fontFamily: "'SF Mono', monospace", // Matching the site's font
      lineHeight: '1.6',
    },
    'pre[class*="language-"]': {
      ...vs['pre[class*="language-"]'],
      background: 'hsl(220, 10%, 98%)', // Matching background
      border: '1px solid hsl(var(--primary))', // Thinner border
      boxShadow: '2px 2px 0px 0px hsl(var(--primary))', // Smaller shadow to match
    },
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
          style={customStyle}
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

  const oldCode = `from datasets import load_dataset
from verdict import Layer, Pipeline
from verdict.common.cot import CoTUnit
from verdict.common.judge import PairwiseJudgeUnit
from verdict import config
from verdict.dataset import DatasetWrapper
from verdict.scale import DiscreteScale
from verdict.schema import Schema
from verdict.transform import MapUnit
from verdict.util import ratelimit

ratelimit.disable()

dataset = DatasetWrapper.from_hf(
    load_dataset("ScalerLab/JudgeBench"),
    lambda row: Schema.of(
        question=row["question"],
        response_A=row["response_A"],
        response_B=row["response_B"],
    ),
    max_samples=10,
)

dataset_inputs = """
<prompt>
{{source.question}}
</prompt>

<response A>
{{source.response_A}}
</response A>

<response B>
{{source.response_B}}
</response B>
""".lstrip()

debate_prompt = f"""
Given the the following prompt and responses, argue why {{option}} is better a response.

{dataset_inputs}
"""

pipeline = (
    Pipeline("Debate")
    >> Layer(
        [
            CoTUnit().prompt(debate_prompt.format(option="Response A")),
            CoTUnit().prompt(debate_prompt.format(option="Response B")),
        ],
    )
    >> MapUnit(
        lambda prev_units_output: Schema.of(
            arguments=f"""
### Argument for Response A:
{prev_units_output[0].thinking}

### Argument for Response B:
{prev_units_output[1].thinking}
"""
        )
    )
    >> PairwiseJudgeUnit(
        options=DiscreteScale(values=["Response A", "Response B"])
    ).prompt(
        f"""
        Given the the following prompt, responses, and arguments in favor of each response, determine which response is better. Respond with either "Response A" or "Response B".

        {dataset_inputs}

        <arguments>
        {{previous.arguments}}
        </arguments>
    """
    )
)

df, leaf_node_columns = pipeline.run_from_dataset(
    dataset["claude"], max_workers=512, display=True, graceful=True
)`;

  const installation = `# using pip...
pip install verdict

# or using uv
conda create -n verdict python=3.13 # we support python >= 3.9
conda activate verdict
uv pip install verdict`;


  const code = `from verdict import Pipeline
from verdict.common.judge import PairwiseJudgeUnit
from verdict.dataset import DatasetWrapper
from verdict.schema import Schema
from verdict.extractor import ArgmaxScoreExtractor
from datasets import load_dataset

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

  return (
    <section className="py-6 fade-in overflow-hidden">
      <div className="mx-auto px-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-4 sm:mb-6">
          <Terminal className="h-5 w-5 sm:h-6 sm:w-6 text-primary" />
          <h2 className="text-2xl sm:text-3xl font-bold">
            Installation & Quickstart
          </h2>
        </div>

        <div className="space-y-6 sm:space-y-8">
          <Card className="hover:shadow-xl transition-all duration-300 bg-popover w-full max-w-full">
            <CardContent className="p-4 sm:p-6 w-full">
              <div className="flex flex-wrap items-center gap-2 mb-3 sm:mb-4">
                <Code2 className="h-5 w-5 text-primary" />
                <h3 className="text-lg sm:text-xl font-semibold">
                  Installation
                </h3>
              </div>
              <div className="bg-transparent rounded-md text-sm overflow-x-auto max-w-full">
                <SyntaxHighlightedContent
                  language="python"
                  content={installation}
                />
              </div>
            </CardContent>
          </Card>

          <Card className="hover:shadow-xl transition-all duration-300 bg-popover w-full max-w-full">
            <CardContent className="p-4 sm:p-6 w-full">
              <div className="flex flex-wrap items-center gap-2 mb-3 sm:mb-4">
                <Rocket className="h-5 w-5 text-primary" />
                <h3 className="text-lg sm:text-xl font-semibold">Quickstart</h3>
              </div>
              <div className="space-y-3 sm:space-y-4">
                <p className="text-muted-foreground text-sm sm:text-base">
                  Get started with a simple example:
                </p>
                <div className="bg-transparent rounded-md text-sm overflow-x-auto max-w-full">
                  <SyntaxHighlightedContent language="python" content={code} />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
};

export default InstallationGuide;

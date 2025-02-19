
import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ChartNoAxesCombined, ChevronDown, ArrowDown } from "lucide-react";

const datasets = {
  ExpertQA: [
    {
      model: "VERDICT (GPT-4o) ⇒ JudgeUnit + JudgeUnit + MaxPoolUnit",
      score: "79.17%",
    },
    { model: "o1", score: "69.91%" },
    {
      model: "VERDICT (GPT-4o-Mini) ⇒ JudgeUnit + JudgeUnit + MaxPoolUnit",
      score: "67.72%",
    },
    { model: "GPT-4o", score: "64.67%" },
    { model: "o3-mini", score: "63.88%" },
    { model: "Claude-3.5 Sonnet", score: "60.9%" },
    { model: "Mistral-Large 2", score: "60.8%" },
    { model: "Qwen2.5-72B-Instruct", score: "60.1%" },
    { model: "QwQ-32B-Preview", score: "60.0%" },
    { model: "GPT-4o-2024-05-13", score: "59.6%" },
    { model: "Bespoke-Minicheck-7B", score: "59.2%" },
    { model: "MiniCheck-Flan-T5-L", score: "59.0%" },
    { model: "Llama-3.1-405B-Instruct", score: "58.5%" },
    { model: "Llama-3.3-70B-Instruct", score: "58.3%" },
    { model: "Tülu-3-70B", score: "55.7%" },
  ],
  XSTest: [
    { model: "VERDICT (GPT-4o) ⇒ CoTUnit + JudgeUnits + MeanPoolUnit", score: "96.44%" },
    { model: "o1", score: "96.00%" },
    { model: "o1 Preview", score: "94.89%" },
    { model: "o1 Mini", score: "95.56%" },
    { model: "GPT-4o", score: "96.00%" },
    { model: "GPT-4o Mini", score: "93.33%" },
    { model: "Claude 3.5 Sonnet", score: "87.33%" },
    { model: "Claude 3 Opus", score: "80.89%" },
    { model: "Claude 3.5 Haiku", score: "84.44%" },
    { model: "WildGuard", score: "95.11%" },
    { model: "Llama-Guard-2-8B", score: "83.56%" },
    { model: "Llama-Guard-3-8B", score: "90.44%" },
  ],
  JudgeBench: [
    { model: "VERDICT (GPT-4o) ⇒ ArgumentUnits + JudgeUnit", score: "63.55%" },
    { model: "o1-preview", score: "75.43%" },
    { model: "o1-mini", score: "65.71%" },
    { model: "GPT-4o", score: "56.57%" },
    { model: "Claude-3.5-Sonnet", score: "64.29%" },
    { model: "Claude-3-Haiku", score: "33.14%" },
    { model: "Llama-3.1-405B-Instruct", score: "56.86%" },
    { model: "Llama-3.1-70B-Instruct", score: "52.29%" },
    { model: "Llama-3.1-8B-Instruct", score: "40.86%" },
    { model: "Gemini-1.5-pro", score: "47.14%" },
    { model: "Gemini-1.5-flash", score: "39.71%" },
    { model: "GPT-4o-mini", score: "50.00%" },
  ],
};

const Results = () => {
  const [selectedDataset, setSelectedDataset] =
    useState<keyof typeof datasets>("ExpertQA");

  const sortedResults = [...datasets[selectedDataset]].sort(
    (a, b) => parseFloat(b.score) - parseFloat(a.score)
  );

  return (
    <section className="py-6 fade-in">
      <div className="mx-auto px-4 sm:px-6">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3 mb-6">
            <ChartNoAxesCombined className="h-6 w-6 text-primary" />
            <h2 className="text-3xl font-semibold">
              Judge Reliability Score
            </h2>
          </div>
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className="w-40 h-8 text-sm justify-between"
              >
                {selectedDataset} <ChevronDown className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-40">
              {Object.keys(datasets).map((dataset) => (
                <Button
                  key={dataset}
                  variant="ghost"
                  className="w-full text-left text-sm py-1"
                  onClick={() =>
                    setSelectedDataset(dataset as keyof typeof datasets)
                  }
                >
                  {dataset}
                </Button>
              ))}
            </PopoverContent>
          </Popover>
        </div>

        <Card className="bg-gray-50 hover:shadow-lg transition-all duration-200">
          <CardContent className="p-4">
            <Table className="text-sm">
              <TableHeader>
                <TableRow>
                  <TableHead className="font-bold">JUDGE</TableHead>
                  <TableHead className="font-bold text-right flex items-center justify-end gap-1">
                    SCORE <ArrowDown className="h-4 w-4 inline-block" />
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedResults.map((result) => (
                  <TableRow
                    key={result.model}
                    className={
                      (selectedDataset === "JudgeBench" && result.model.startsWith("VERDICT")) ||
                        ((selectedDataset === "ExpertQA" || selectedDataset === "XSTest") &&
                          result.model.startsWith("VERDICT") &&
                          result.score === sortedResults[0].score)
                        ? "bg-primary/10"
                        : ""
                    }
                  >
                    <TableCell
                      className={
                        (selectedDataset === "JudgeBench" && result.model.startsWith("VERDICT")) ||
                          ((selectedDataset === "ExpertQA" || selectedDataset === "XSTest") &&
                            result.model.startsWith("VERDICT") &&
                            result.score === sortedResults[0].score)
                          ? "font-bold text-primary"
                          : ""
                      }
                    >
                      {result.model}
                    </TableCell>
                    <TableCell
                      className={`text-right ${(selectedDataset === "JudgeBench" && result.model.startsWith("VERDICT")) ||
                          ((selectedDataset === "ExpertQA" || selectedDataset === "XSTest") &&
                            result.model.startsWith("VERDICT") &&
                            result.score === sortedResults[0].score)
                          ? "font-bold text-primary"
                          : ""
                        }`}
                    >
                      {result.score}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </section>
  );
};

export default Results;

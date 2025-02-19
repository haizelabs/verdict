
import { useEffect, useState } from "react";
import Hero from "@/components/Hero";
import Abstract from "@/components/Abstract";
import Features from "@/components/Features";
import InstallationGuide from "@/components/InstallationGuide";
import Results from "@/components/Results";
import Applications from "@/components/Applications";
import WhyUseVerdict from "@/components/WhyUseVerdict";

const sections = [
  { id: "installation-guide", label: "Installation" },
  { id: "results", label: "Results" },
  { id: "applications", label: "Applications" },
  { id: "why-use-verdict", label: "Why Verdict" },
  { id: "features", label: "Features" },
];

const TableOfContents = ({ sections }) => {
  const [activeSection, setActiveSection] = useState("");

  useEffect(() => {
    const handleScroll = () => {
      let bestMatch = "";
      let maxVisibleRatio = 0;

      sections.forEach(({ id }) => {
        const section = document.getElementById(id);
        if (section) {
          const rect = section.getBoundingClientRect();
          const sectionHeight = rect.bottom - rect.top;
          const visibleHeight = Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0));
          const visibilityRatio = visibleHeight / sectionHeight;

          if (visibilityRatio > maxVisibleRatio) {
            maxVisibleRatio = visibilityRatio;
            bestMatch = id;
          }
        }
      });

      setActiveSection(bestMatch);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <div className="hidden xl:block fixed top-24 right-6 card-retro p-4 w-56 z-50 transition-all duration-300">
      <h3 className="text-lg font-semibold mb-4 text-primary tracking-wide">📌 Contents</h3>
      <ul className="space-y-3">
        {sections.map(({ id, label }) => (
          <li key={id}>
            <button
              onClick={() => scrollToSection(id)}
              className={`w-full text-left px-3 py-2 transition-all duration-300 border-2 ${
                activeSection === id
                  ? "border-primary bg-primary/10 text-primary font-medium translate-x-1"
                  : "border-transparent hover:border-primary/50 hover:bg-primary/5"
              }`}
            >
              {label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
};

const Index = () => {
  return (
    <div className="min-h-screen w-full overflow-hidden">
      <main className="w-full mx-auto px-4 lg:px-8 flex flex-col items-center">
        <Hero />
        <div className="w-full flex flex-wrap xl:flex-nowrap justify-center gap-8 lg:gap-16 relative">
          <TableOfContents sections={sections} />
          <div className="w-full max-w-6xl">
            <div id="installation-guide" className="scroll-mt-24">
              <InstallationGuide />
            </div>
            <div id="results" className="scroll-mt-24">
              <Results />
            </div>
            <div id="applications" className="scroll-mt-24">
              <Applications />
            </div>
            <div id="why-use-verdict" className="scroll-mt-24">
              <WhyUseVerdict />
            </div>
            <div id="features" className="scroll-mt-24 relative">
              <Features />
              <div id="verdict-core-features" className="absolute top-0"></div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Index;

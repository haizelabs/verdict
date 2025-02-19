import { useEffect, useState } from "react";
import Hero from "@/components/Hero";
import Abstract from "@/components/Abstract";
import Features from "@/components/Features";
import InstallationGuide from "@/components/InstallationGuide";
import Results from "@/components/Results";

const sections = [
  { id: "installation-guide", label: "Installation Guide" },
  { id: "results", label: "Results" },
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
          const visibilityRatio = visibleHeight / sectionHeight; // Percentage of section visible

          // Prioritize sections that are mostly visible
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

  return (
    <div className="hidden md:block fixed top-24 right-6 bg-white shadow-lg p-4 rounded-2xl border border-gray-300 w-56 z-50 transition-all duration-300 hover:shadow-xl">
      <h3 className="text-lg font-semibold mb-2 text-gray-800">📌 Table of Contents</h3>
      <ul className="space-y-2">
        {sections.map(({ id, label }) => (
          <li key={id}>
            <a
              href={`#${id}`}
              className={`block px-3 py-1 rounded-lg transition-all ${activeSection === id
                  ? "font-bold bg-blue-100 text-blue-600"
                  : "text-gray-600 hover:bg-gray-100"
                }`}
            >
              {label}
            </a>
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
        <div className="w-full flex flex-wrap md:flex-nowrap justify-center gap-8 lg:gap-16 relative">
          <TableOfContents sections={sections} />
          <div className="w-full max-w-6xl">
            <div id="installation-guide" className="scroll-mt-24">
              <InstallationGuide />
            </div>
            <div id="results" className="scroll-mt-24">
              <Results />
            </div>
            <div id="features" className="scroll-mt-24 relative">
              <Features />
              {/* Ensuring nested sections inside Features are also detected */}
              <div id="verdict-core-features" className="absolute top-0"></div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Index;

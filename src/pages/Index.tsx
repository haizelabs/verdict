import Hero from "@/components/Hero";
import Abstract from "@/components/Abstract";
import Features from "@/components/Features";
import InstallationGuide from "@/components/InstallationGuide";
import Results from "@/components/Results";

const Index = () => {
  return (
    <div className="min-h-screen w-full overflow-hidden">
      <main className="w-full max-w-screen-2xl mx-auto px-4 lg:px-8">
        <Hero />
        <div className="flex flex-wrap md:flex-nowrap justify-center gap-8 lg:gap-16">
          <div className="flex flex-col w-full md:w-1/2">
            <Abstract />
            <Results />
          </div>
          <div className="flex flex-col w-full md:w-1/2">
            <InstallationGuide />
          </div>
        </div>
        <Features />
      </main>
    </div>
  );
};

export default Index;

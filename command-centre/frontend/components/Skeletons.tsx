"use client";

export const AlertsSkeleton = () => (
  <div className="w-full h-full flex flex-col p-6 animate-pulse">
    <div className="flex justify-between items-end mb-6">
       <div className="h-8 w-24 bg-zinc-800 rounded"></div>
       <div className="h-3 w-16 bg-zinc-800/50 rounded"></div>
    </div>
    <div className="h-16 w-full bg-zinc-800/50 rounded-xl mb-2"></div>
    <div className="flex justify-between mb-8">
       <div className="h-2 w-8 bg-zinc-800/50 rounded"></div>
       <div className="h-2 w-8 bg-zinc-800/50 rounded"></div>
    </div>
    
    <div className="h-4 w-32 bg-zinc-800 rounded mb-4"></div>
    <div className="space-y-4">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-12 w-full bg-zinc-800/30 border border-zinc-800/50 rounded flex items-center px-4">
           <div className="h-4 w-4 rounded-full bg-zinc-700 mr-3"></div>
           <div className={`h-3 ${i % 2 === 0 ? 'w-1/2' : 'w-2/3'} bg-zinc-700 rounded`}></div>
        </div>
      ))}
    </div>
  </div>
);

export const ResearchSkeleton = () => (
  <div className="w-full h-full p-8 flex flex-col animate-pulse">
    <div className="h-6 w-48 bg-zinc-800 rounded mb-2"></div>
    <div className="h-3 w-96 bg-zinc-800/50 rounded mb-10"></div>
    
    <div className="grid grid-cols-3 gap-6 flex-1">
       {[...Array(3)].map((_, i) => (
         <div key={i} className="bg-zinc-800/30 border border-zinc-800/50 rounded-xl p-6 flex flex-col">
           <div className="h-5 w-32 bg-zinc-700 rounded mb-6"></div>
           <div className="h-32 w-full bg-zinc-800/50 rounded-xl mb-4"></div>
           <div className="space-y-3">
             <div className="h-3 w-full bg-zinc-800 rounded"></div>
             <div className="h-3 w-5/6 bg-zinc-800 rounded"></div>
           </div>
         </div>
       ))}
    </div>
  </div>
);

export const DisruptSkeleton = () => (
  <div className="w-full h-full p-8 flex flex-col animate-pulse">
    <div className="h-6 w-56 bg-zinc-800 rounded mb-2"></div>
    <div className="h-3 w-80 bg-zinc-800/50 rounded mb-10"></div>
    
    <div className="flex justify-between items-end mb-4 border-b border-zinc-800/50 pb-2">
       <div className="h-4 w-24 bg-zinc-800 rounded"></div>
       <div className="h-4 w-32 bg-zinc-800 rounded"></div>
    </div>
    
    <div className="space-y-3 flex-1 overflow-hidden">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="flex items-center justify-between bg-zinc-800/20 border border-zinc-800/50 p-4 rounded-lg">
           <div className="flex gap-4 items-center">
             <div className="h-8 w-8 bg-zinc-700 rounded-md"></div>
             <div className="space-y-2">
               <div className="h-4 w-48 bg-zinc-700 rounded"></div>
               <div className="h-3 w-32 bg-zinc-800 rounded"></div>
             </div>
           </div>
           <div className="h-8 w-24 bg-zinc-700 rounded-md"></div>
        </div>
      ))}
    </div>
  </div>
);

export const MetricsSkeleton = () => (
  <div className="w-full h-full flex animate-pulse">
    <div className="w-64 border-r border-zinc-800/50 p-6 flex flex-col gap-6">
       <div className="h-5 w-32 bg-zinc-800 rounded"></div>
       <div className="space-y-3">
         {[...Array(4)].map((_, i) => (
           <div key={i} className="h-10 w-full bg-zinc-800/50 rounded-md"></div>
         ))}
       </div>
    </div>
    <div className="flex-1 p-8 flex flex-col">
       <div className="h-8 w-64 bg-zinc-800 rounded mb-4"></div>
       <div className="h-3 w-96 bg-zinc-800/50 rounded mb-10"></div>
       
       <div className="grid grid-cols-2 gap-6 mb-8">
         {[...Array(2)].map((_, i) => (
           <div key={i} className="h-24 bg-zinc-800/30 border border-zinc-800/50 rounded-xl p-4 flex flex-col justify-between">
              <div className="h-4 w-24 bg-zinc-700 rounded"></div>
              <div className="h-8 w-16 bg-zinc-600 rounded"></div>
           </div>
         ))}
       </div>
       
       <div className="flex-1 w-full bg-zinc-800/30 border border-zinc-800/50 rounded-xl"></div>
    </div>
  </div>
);

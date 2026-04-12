import Link from 'next/link';
import { ShieldAlert, LayoutDashboard, Settings } from 'lucide-react';

export default function Sidebar({ activePage }: { activePage: string }) {
  return (
    <div className="fixed left-0 top-0 bottom-0 w-16 bg-[#111113] border-r border-white/5 flex flex-col items-center py-6 z-50">
      <Link href="/" className="mb-8">
        <ShieldAlert className="w-6 h-6 text-[#D6B36A]" />
      </Link>
      
      <div className="flex flex-col gap-4">
        <Link href="/dashboard" className={`p-3 rounded-xl transition-all ${activePage === 'dashboard' ? 'bg-[#D6B36A]/10 text-[#D6B36A]' : 'text-[#71717A] hover:bg-[#161618] hover:text-[#EAEAEA]'}`}>
          <LayoutDashboard className="w-5 h-5" />
        </Link>
        <Link href="/dashboard/settings" className={`p-3 rounded-xl transition-all ${activePage === 'settings' ? 'bg-[#D6B36A]/10 text-[#D6B36A]' : 'text-[#71717A] hover:bg-[#161618] hover:text-[#EAEAEA]'}`}>
          <Settings className="w-5 h-5" />
        </Link>
      </div>
      
      <div className="mt-auto">
        <div className="w-8 h-8 rounded-full bg-[#161618] flex items-center justify-center text-[#EAEAEA] text-xs font-bold border border-white/10">
          AF
        </div>
      </div>
    </div>
  );
}

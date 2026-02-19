import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="page-container">
      <h1 className="page-title">页面不存在</h1>
      <p className="page-subtitle">请从导航返回可用页面。</p>
      <div className="mt-4">
        <Link href="/">
          <Button>返回 Plan</Button>
        </Link>
      </div>
    </main>
  );
}

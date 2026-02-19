import { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type AlertProps = HTMLAttributes<HTMLDivElement> & {
  variant?: "default" | "destructive";
};

export function Alert({ className, variant = "default", ...props }: AlertProps) {
  return (
    <div
      className={cn(
        "w-full rounded-md border px-4 py-3 text-sm",
        variant === "destructive"
          ? "border-destructive/40 bg-destructive/10 text-destructive"
          : "border-border bg-muted/50 text-foreground",
        className
      )}
      {...props}
    />
  );
}

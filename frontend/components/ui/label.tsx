import { LabelHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

const Label = forwardRef<HTMLLabelElement, LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => {
    return <label ref={ref} className={cn("text-sm font-medium", className)} {...props} />;
  }
);
Label.displayName = "Label";

export { Label };

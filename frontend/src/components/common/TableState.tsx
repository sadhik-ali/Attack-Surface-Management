import { Search } from "lucide-react";

import { Input, Skeleton, Table, TBody, Td, Tr } from "@/components/ui";
import { cn } from "@/lib/utils";

export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("w-full sm:max-w-xs", className)}>
      <Input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        leftAddon={<Search aria-hidden="true" className="h-3.5 w-3.5" />}
      />
    </div>
  );
}

export function TableLoading({
  columns,
  rows = 6,
}: {
  columns: number;
  rows?: number;
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TBody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <Tr key={rowIndex} className="hover:bg-transparent">
              {Array.from({ length: columns }).map((__, columnIndex) => (
                <Td key={columnIndex}>
                  <Skeleton
                    className={cn("h-4", columnIndex === 0 ? "w-40" : "w-20")}
                  />
                </Td>
              ))}
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

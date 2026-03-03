import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent Inventory — Aviation Multi-Agent Solver",
};

export default function InventoryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}

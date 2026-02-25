"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Plane, PanelLeftClose, PanelLeft, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAviationStore } from "@/store/aviation-store";
import { useSSE } from "@/hooks/use-sse";
import { ScenarioCards } from "./scenario-cards";
import type { ChatMessage, AgentInfo } from "@/types/aviation";
import { chatMessage } from "@/lib/animation-variants";

export function ChatSidebar() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Describe an airline operations issue. I will launch an agent-framework run, stream traces over SSE, and show which Azure/Fabric datastores each agent used.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    currentRunId,
    setCurrentRunId,
    initializeAgents,
    sidebarCollapsed,
    setSidebarCollapsed,
    events,
  } = useAviationStore();

  const { reconnecting } = useSSE({ runId: currentRunId || "", enabled: !!currentRunId });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (text?: string) => {
    const messageText = (text || input).trim();
    if (!messageText || isLoading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: messageText,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/av/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messageText }),
      });

      const data = await response.json();
      if (response.ok) {
        const assistantMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: data.response || data.message || "Processing...",
        };
        setMessages((prev) => [...prev, assistantMessage]);

        if (data.run_id) setCurrentRunId(data.run_id);
        if (data.agents && data.scenario) {
          initializeAgents(data.agents as AgentInfo[], data.scenario as string);
        }
      } else {
        setMessages((prev) => [
          ...prev,
          { id: (Date.now() + 1).toString(), role: "assistant", content: "Error processing your request." },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: (Date.now() + 1).toString(), role: "assistant", content: "Connection error. Check backend availability." },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  if (sidebarCollapsed) {
    return (
      <div className="flex w-12 flex-col items-center border-r border-av-sky/14 bg-av-surface/40 py-3">
        <button onClick={() => setSidebarCollapsed(false)} className="rounded-md p-2 transition hover:bg-av-sky/10" aria-label="Expand sidebar">
          <PanelLeft className="w-4 h-4 text-muted-foreground" />
        </button>
        <div className="mt-4 rounded-md border border-av-sky/25 bg-av-sky/12 p-1.5">
          <Bot className="w-4 h-4 text-av-sky" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col border-r border-av-sky/14 bg-gradient-to-b from-av-surface/78 to-av-midnight/72">
      <div className="flex items-center justify-between border-b border-av-sky/20 bg-gradient-to-r from-av-sky/14 via-av-fabric/8 to-transparent px-3 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-av-sky/35 bg-av-sky/20">
            <Bot className="w-4 h-4 text-av-sky" />
          </div>
          <div>
            <p className="text-xs font-semibold">Operations Console</p>
            <p className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">Agent Framework + SSE</p>
          </div>
        </div>
        <button onClick={() => setSidebarCollapsed(true)} className="rounded p-1 transition hover:bg-av-sky/10" aria-label="Collapse sidebar">
          <PanelLeftClose className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
      </div>

      <div className="flex items-center justify-between border-b border-av-sky/18 px-3 py-2 text-[10px]">
        <span className="text-muted-foreground">{events.length} traces</span>
        <span className="av-pill">
          <Radio className="w-2.5 h-2.5" />
          {currentRunId ? "Run active" : "Ready"}
        </span>
      </div>

      {reconnecting && (
        <div className="border-b border-av-gold/30 bg-av-gold/10 px-3 py-1.5 text-center">
          <span className="text-[11px] text-av-gold font-medium">Reconnecting SSE stream...</span>
        </div>
      )}

      <div className="av-scroll flex-1 space-y-3 overflow-y-auto p-3">
        <AnimatePresence>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              variants={chatMessage}
              initial="hidden"
              animate="visible"
              className={`flex gap-2 ${message.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 ${
                  message.role === "user" ? "border border-av-sky/35 bg-av-sky" : "border border-av-sky/25 bg-av-sky/18"
                }`}
              >
                {message.role === "user" ? (
                  <User className="w-3 h-3 text-av-navy" />
                ) : (
                  <Plane className="w-3 h-3 text-av-sky" />
                )}
              </div>
              <div
                className={`max-w-[88%] p-2.5 rounded-lg text-xs leading-relaxed ${
                  message.role === "user"
                    ? "border border-av-sky/40 bg-gradient-to-r from-av-sky to-sky-300 text-av-navy font-semibold shadow-[0_8px_24px_rgba(14,165,233,0.25)]"
                    : "border border-av-sky/15 bg-av-midnight/76"
                }`}
              >
                {message.content}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {isLoading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md border border-av-sky/25 bg-av-sky/18">
              <Plane className="w-3 h-3 text-av-sky" />
            </div>
            <div className="rounded-lg border border-av-sky/20 bg-av-midnight/80 p-2">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-av-sky rounded-full animate-bounce" />
                <span className="w-1.5 h-1.5 bg-av-sky rounded-full animate-bounce [animation-delay:120ms]" />
                <span className="w-1.5 h-1.5 bg-av-sky rounded-full animate-bounce [animation-delay:240ms]" />
              </div>
            </div>
          </motion.div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {!currentRunId && messages.length <= 2 && (
        <div className="border-t border-av-sky/20 px-3 py-2">
          <ScenarioCards onSelect={(prompt) => handleSend(prompt)} />
        </div>
      )}

      <div className="border-t border-av-sky/20 p-3">
        <div className="flex gap-1.5">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Describe a disruption..."
            disabled={isLoading}
            className="av-input flex-1 rounded-md px-3 py-2 text-xs transition focus:outline-none focus:ring-1 focus:ring-av-sky disabled:opacity-50"
          />
          <Button
            size="sm"
            onClick={() => handleSend()}
            disabled={!input.trim() || isLoading}
            className="h-8 w-8 border border-av-sky/35 bg-gradient-to-r from-av-sky to-sky-300 p-0 text-av-navy hover:brightness-110"
          >
            <Send className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

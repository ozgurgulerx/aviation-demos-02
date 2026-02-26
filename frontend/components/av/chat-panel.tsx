"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Plane } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAviationStore } from "@/store/aviation-store";
import { useSSE } from "@/hooks/use-sse";
import type { ChatMessage } from "@/types/aviation";

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm your aviation operations assistant. Describe a problem — flight disruptions, crew scheduling conflicts, maintenance issues — and I'll coordinate a multi-agent analysis to find the best solution.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { currentRunId, setCurrentRunId } = useAviationStore();

  // Connect SSE when we have a run
  useSSE({ runId: currentRunId || "", enabled: !!currentRunId });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const messageText = input.trim();

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: messageText,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // Send to solve endpoint to kick off multi-agent workflow
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
          content: data.response || data.message || "Processing your request...",
        };
        setMessages((prev) => [...prev, assistantMessage]);

        // If we got a run_id back, start SSE connection
        if (data.run_id) {
          setCurrentRunId(data.run_id);
        }
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: (Date.now() + 1).toString(),
            role: "assistant",
            content: "Sorry, I encountered an error processing your request. Please try again.",
          },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content:
            "I'm having trouble connecting to the backend. Make sure the server is running on port 5001.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const suggestions = [
    "Flight AA1234 diverted due to weather, 200 passengers need rebooking",
    "Crew scheduling conflict for morning departures at JFK",
    "Maintenance alert on Boeing 737 fleet, check safety compliance",
    "Three flights delayed due to ATC ground stop, optimize recovery",
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Chat Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center">
          <Bot className="w-4 h-4 text-white" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-sm">Aviation Problem Solver</h3>
          <p className="text-xs text-muted-foreground">Describe your problem</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <AnimatePresence>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${message.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  message.role === "user"
                    ? "bg-primary"
                    : "bg-gradient-to-br from-blue-500 to-indigo-500"
                }`}
              >
                {message.role === "user" ? (
                  <User className="w-4 h-4 text-white" />
                ) : (
                  <Plane className="w-4 h-4 text-white" />
                )}
              </div>
              <div
                className={`max-w-[80%] p-3 rounded-xl text-sm ${
                  message.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                {message.content}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex gap-3"
          >
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center">
              <Plane className="w-4 h-4 text-white" />
            </div>
            <div className="bg-muted p-3 rounded-xl">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:100ms]" />
                <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:200ms]" />
              </div>
            </div>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 2 && (
        <div className="px-4 py-3 border-t">
          <p className="text-xs text-muted-foreground mb-2">Try asking:</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => setInput(suggestion)}
                className="text-xs px-3 py-1.5 rounded-full bg-muted hover:bg-accent transition-colors text-left"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-4 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Describe an aviation problem..."
            disabled={isLoading}
            className="flex-1 px-4 py-2.5 rounded-lg bg-muted border border-border focus:outline-none focus:ring-2 focus:ring-ring text-sm disabled:opacity-50"
          />
          <Button onClick={handleSend} disabled={!input.trim() || isLoading}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

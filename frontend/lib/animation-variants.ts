import type { Variants } from "framer-motion";

export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.85 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.3, ease: "easeOut" } },
};

export const agentActivate: Variants = {
  idle: { scale: 1, opacity: 1 },
  activate: {
    scale: [1, 1.08, 1],
    opacity: 1,
    transition: { duration: 0.5, ease: "easeInOut" },
  },
};

export const glowPulse: Variants = {
  idle: { opacity: 0.3, scale: 1 },
  active: {
    opacity: [0.3, 0.7, 0.3],
    scale: [1, 1.06, 1],
    transition: { duration: 2, repeat: Infinity, ease: "easeInOut" },
  },
};

export const slidePanel: Variants = {
  hidden: { x: 480, opacity: 0 },
  visible: {
    x: 0,
    opacity: 1,
    transition: { type: "spring", damping: 25, stiffness: 250 },
  },
  exit: { x: 480, opacity: 0, transition: { duration: 0.2 } },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.06 },
  },
};

export const chatMessage: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.25 } },
};

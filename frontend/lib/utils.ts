import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { JsonCard } from "../types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Parses a text stream and extracts JSONCARD blocks.
 * Returns the cleaned text (markdown), an array of parsed Card objects,
 * and a flag indicating if there's an incomplete JSONCARD being received.
 * 
 * 支持多种格式：
 * 1. ```JSONCARD [...] ``` (标准格式)
 * 2. JSONCARD [...] (无反引号格式)
 */
export function parseContentWithCards(text: string): {
  cleanText: string;
  cards: JsonCard[];
  hasIncompleteCard: boolean;
} {
  const cards: JsonCard[] = [];
  let hasIncompleteCard = false;

  // 正则表达式同时匹配两种完整格式
  // 格式1: ```JSONCARD ... ```
  // 格式2: JSONCARD [...]
  const cardRegex = /(?:```JSONCARD\s*([\s\S]*?)\s*```|JSONCARD\s*(\[[\s\S]*?\])(?:\s*$|\n))/g;

  // 首先处理完整的 JSONCARD
  let cleanText = text.replace(cardRegex, (match, jsonString1, jsonString2) => {
    const jsonString = jsonString1 || jsonString2;
    if (!jsonString) return match;

    try {
      const parsed = JSON.parse(jsonString);
      if (Array.isArray(parsed)) {
        cards.push(...parsed);
      } else {
        cards.push(parsed);
      }
    } catch (e) {
      console.error("Failed to parse JSONCARD", e, jsonString);
      return match;
    }
    return ""; // Remove from visible text stream
  });

  // 检测未完成的 JSONCARD 模式
  // 模式1: 以 ```JSONCARD 开头但没有结束的 ```
  // 模式2: 以 JSONCARD [ 开头但 JSON 不完整
  // 模式3: 以 [{ 开头的 JSON 数组（可能是 paper_result 等）
  const incompletePatterns = [
    /```JSONCARD\s*[\s\S]*$/,           // 未闭合的 ```JSONCARD
    /JSONCARD\s*\[[\s\S]*$/,             // 未闭合的 JSONCARD [
    /\[\s*\{\s*"type"\s*:\s*"[^"]+"/,    // 以 [{"type": "xxx" 开头的 JSON
  ];

  for (const pattern of incompletePatterns) {
    if (pattern.test(cleanText)) {
      // 检查是否是不完整的 JSON（尝试解析会失败）
      const match = cleanText.match(pattern);
      if (match) {
        const potentialJson = match[0];
        // 尝试提取 JSON 部分
        const jsonMatch = potentialJson.match(/\[[\s\S]*/);
        if (jsonMatch) {
          try {
            JSON.parse(jsonMatch[0]);
            // 如果能解析，说明是完整的，不需要处理
          } catch {
            // 解析失败，说明是不完整的 JSONCARD
            hasIncompleteCard = true;
            // 用 loading 占位符替换不完整的部分
            cleanText = cleanText.replace(pattern, '\n\n[LOADING_CARD]\n\n');
            break;
          }
        }
      }
    }
  }

  return { cleanText, cards, hasIncompleteCard };
}

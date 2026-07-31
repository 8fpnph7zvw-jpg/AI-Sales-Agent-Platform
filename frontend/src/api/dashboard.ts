import { getConversationMessages, getConversations } from "./conversations";
import { getCustomers } from "./customers";
import { getProducts, getQuotations } from "./quotations";
import type {
  Conversation,
  Customer,
  DashboardInsights,
  Message,
  Product,
  Quotation,
} from "@/types/business";

function localDateKey(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function regionName(countryCode: string | null): string {
  if (countryCode === "US") return "美国";
  if (["SG", "MY", "TH", "VN", "ID", "PH", "KH", "LA", "MM", "BN"].includes(countryCode || "")) {
    return "东南亚";
  }
  if (["DE", "FR", "IT", "ES", "NL", "BE", "SE", "NO", "DK", "FI", "PL", "AT", "IE", "PT", "CZ", "GR", "RO", "HU"].includes(countryCode || "")) {
    return "欧洲";
  }
  return countryCode ? "其他地区" : "地区待完善";
}

export async function getDashboardInsights(): Promise<DashboardInsights> {
  const responses = await Promise.allSettled([
    getCustomers({ limit: 100, offset: 0 }),
    getConversations({ limit: 100, offset: 0 }),
    getQuotations({ limit: 100, offset: 0 }),
    getProducts({ limit: 100, offset: 0 }),
  ]);
  if (responses.every((response) => response.status === "rejected")) {
    throw (responses[0] as PromiseRejectedResult).reason;
  }

  const customers = responses[0].status === "fulfilled"
    ? (responses[0].value.data as Customer[])
    : [];
  const conversations = responses[1].status === "fulfilled"
    ? (responses[1].value.data as Conversation[])
    : [];
  const quotations = responses[2].status === "fulfilled"
    ? (responses[2].value.data as Quotation[])
    : [];
  const products = responses[3].status === "fulfilled"
    ? (responses[3].value.data as Product[])
    : [];

  const messageResponses = await Promise.allSettled(
    conversations.slice(0, 30).map((conversation) =>
      getConversationMessages(conversation.id, { limit: 200 }),
    ),
  );
  const messages = messageResponses.flatMap((response) =>
    response.status === "fulfilled" ? response.value.data : [],
  ) as Message[];
  const today = localDateKey(new Date());
  const todayMessages = messages.filter((message) => localDateKey(message.created_at) === today);
  const inboundToday = todayMessages.filter(
    (message) => message.direction === "inbound" || message.sender_type === "customer",
  );
  const aiToday = todayMessages.filter((message) => message.sender_type === "ai");

  const regionCounts = new Map<string, number>();
  customers.forEach((customer) => {
    const region = regionName(customer.country_code);
    regionCounts.set(region, (regionCounts.get(region) || 0) + 1);
  });

  const inquiryContent = [
    ...messages
      .filter((message) => message.direction === "inbound" || message.sender_type === "customer")
      .map((message) => message.content),
    ...conversations.map((conversation) => conversation.last_message_preview || ""),
  ].join("\n").toLocaleLowerCase();
  const popularProducts = products
    .map((product) => ({
      name: product.name,
      unit: product.unit,
      inquiries: inquiryContent.split(product.name.toLocaleLowerCase()).length - 1,
    }))
    .filter((product) => product.inquiries > 0)
    .sort((left, right) => right.inquiries - left.inquiries)
    .slice(0, 5);

  const trend = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    const key = localDateKey(date);
    const dailyMessages = messages.filter((message) => localDateKey(message.created_at) === key);
    return {
      date: key,
      inquiries: dailyMessages.filter(
        (message) => message.direction === "inbound" || message.sender_type === "customer",
      ).length,
      ai_replies: dailyMessages.filter((message) => message.sender_type === "ai").length,
    };
  });

  return {
    today_visitors: customers.filter((customer) => localDateKey(customer.created_at) === today).length,
    ai_handled_today: aiToday.length,
    pending_follow_up: customers.filter((customer) =>
      ["new", "lead", "qualified", "follow_up"].includes(customer.lifecycle_stage),
    ).length,
    won_opportunities: quotations.filter((quotation) =>
      ["approved", "accepted", "won"].includes(quotation.status),
    ).length,
    identified_customers_today: new Set(inboundToday.map((message) => message.conversation_id)).size,
    high_intent_customers: customers.filter((customer) =>
      ["hot", "high"].includes(customer.intent_level || ""),
    ).length,
    region_distribution: Array.from(regionCounts, ([name, value]) => ({ name, value }))
      .sort((left, right) => right.value - left.value),
    popular_products: popularProducts,
    trend,
  };
}

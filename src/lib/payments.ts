export type PaymentResult = { redirectUrl?: string; success?: boolean; data?: any };

export interface PaymentProvider {
  createPayment: (order: { id: string; amount: number; meta?: any }) => Promise<PaymentResult>;
  verifyPayment: (params: any) => Promise<PaymentResult>;
}

// Export a registry
const providers: Record<string, PaymentProvider> = {};
export function registerProvider(name: string, impl: PaymentProvider) {
  providers[name] = impl;
}
export function getProvider(name: string) {
  return providers[name];
}

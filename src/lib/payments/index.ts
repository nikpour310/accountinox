export type PaymentProvider = {
  createPayment: (order: { id: string; amount: number }) => Promise<{ redirectUrl: string }>;
  verifyPayment: (params: any) => Promise<{ success: boolean; data?: any }>;
};

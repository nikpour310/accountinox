import axios from 'axios';
import { PaymentProvider } from '..';

export const ZarinpalProvider: PaymentProvider = {
  async createPayment({ id, amount }) {
    // stub implementation, real integration requires merchant id and proper callbacks
    const url = `https://www.zarinpal.com/pg/StartPay/${id}`;
    return { redirectUrl: url };
  },
  async verifyPayment(params: any) {
    // stub
    return { success: true, data: params };
  }
};

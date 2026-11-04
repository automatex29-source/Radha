/** The platform fee added at checkout, in whole rupees, so the customer pays Razorpay's fee. Worked out exactly
 *  like billing.platform_fee on the server: `pct` of the total (price + GST), covering the fee on itself, rounded up. */
export function platformFee(rupees, pct) {
  if (!pct || rupees <= 0) return 0;
  return Math.ceil((Math.round(rupees * 100) * pct) / (100 - pct) / 100);
}

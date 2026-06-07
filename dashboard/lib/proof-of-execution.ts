/** Static proof-of-execution record from NEXT_PUBLIC_* env (build-time, no runtime fetch). */

export type ProofOfExecutionRecord = {
  txHash: string;
  tool: string;
  asset: string;
  amount: string;
  timestamp: string;
  timestampDate: Date | null;
  network: string;
  explorerUrl: string;
};

export function getProofOfExecution(): ProofOfExecutionRecord | null {
  const txHash = (process.env.NEXT_PUBLIC_PROOF_TX_HASH ?? "").trim();
  if (!txHash) return null;

  const timestamp = (process.env.NEXT_PUBLIC_PROOF_TIMESTAMP ?? "").trim();
  let timestampDate: Date | null = null;
  if (timestamp) {
    const parsed = new Date(timestamp);
    if (!Number.isNaN(parsed.getTime())) timestampDate = parsed;
  }

  return {
    txHash,
    tool: (process.env.NEXT_PUBLIC_PROOF_TX_TYPE ?? "transfer_send").trim() || "transfer_send",
    asset: (process.env.NEXT_PUBLIC_PROOF_ASSET ?? "USDT").trim() || "USDT",
    amount: (process.env.NEXT_PUBLIC_PROOF_AMOUNT ?? "").trim(),
    timestamp,
    timestampDate,
    network: (process.env.NEXT_PUBLIC_PROOF_NETWORK ?? "Injective Testnet").trim(),
    explorerUrl: `https://testnet.explorer.injective.network/transaction/${txHash}`,
  };
}

/** Middle-truncate for monospace display (mobile-safe). */
export function truncateTxHash(hash: string, head = 10, tail = 8): string {
  if (hash.length <= head + tail + 3) return hash;
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

export function txExplorerUrl(network: string | undefined, txHash: string): string {
  const hash = txHash.replace(/^0x/i, "");
  const isMainnet = network === "mainnet" || network === "injective-1";
  const base = isMainnet
    ? "https://explorer.injective.network/transaction"
    : "https://testnet.explorer.injective.network/transaction";
  return `${base}/${hash.startsWith("0x") ? hash : `0x${hash}`}`;
}

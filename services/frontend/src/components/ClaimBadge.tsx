import Badge from "./ui/Badge";

export default function ClaimBadge({
  claim,
  mine,
}: {
  claim: { held: boolean; username: string | null } | undefined;
  mine: boolean;
}) {
  if (!claim || !claim.held) {
    return <Badge tone="neutral">FREE</Badge>;
  }
  if (mine) {
    return <Badge tone="success">YOURS</Badge>;
  }
  return <Badge tone="warning">Held by {claim.username}</Badge>;
}

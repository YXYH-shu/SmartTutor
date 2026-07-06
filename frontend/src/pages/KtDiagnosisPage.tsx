const DEFAULT_CHATAGENT_URL = 'http://127.0.0.1:8910/';

function withEmbedMode(url: string) {
  const parsed = new URL(url, window.location.href);
  parsed.searchParams.set('embed', '1');
  return parsed.toString();
}

export default function KtDiagnosisPage() {
  const chatAgentUrl =
    import.meta.env.VITE_KT_CHATAGENT_URL?.trim() || DEFAULT_CHATAGENT_URL;
  const iframeUrl = withEmbedMode(chatAgentUrl);

  return (
    <div className="h-full w-full overflow-hidden bg-[#0a0a0f]">
      <iframe
        src={iframeUrl}
        title="学情分析"
        className="h-full w-full border-0"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}

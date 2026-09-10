import { FilePreviewPresentationProvider } from "@/components/agentscope-chat/FilePreviewPresentationContext";

export default function ReportView() {
  return (
    <FilePreviewPresentationProvider value="modal">
      <div>
        <h1>ReportView</h1>
      </div>
    </FilePreviewPresentationProvider>
  );
}

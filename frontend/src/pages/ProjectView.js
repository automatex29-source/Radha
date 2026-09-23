import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  ArrowLeft, Upload, FileText, Trash2, MessageSquare, Plus, Brain, Loader2, Save,
  CheckCircle2, AlertCircle, Clock,
} from "lucide-react";

const STATUS = {
  ready: { icon: CheckCircle2, cls: "text-emerald-400", label: "Ready" },
  processing: { icon: Clock, cls: "text-amber-400", label: "Processing" },
  failed: { icon: AlertCircle, cls: "text-red-400", label: "Failed" },
};

export default function ProjectView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [instructions, setInstructions] = useState("");
  const [savingInst, setSavingInst] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [memInput, setMemInput] = useState("");
  const fileRef = useRef(null);

  const load = async () => {
    try {
      const res = await api.get(`/projects/${id}`);
      setData(res.data);
      setInstructions(res.data.project.instructions || "");
    } catch (e) {
      toast.error(formatApiError(e));
      navigate("/projects");
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const saveInstructions = async () => {
    setSavingInst(true);
    try {
      await api.patch(`/projects/${id}`, { instructions });
      toast.success("Instructions saved");
      load();
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setSavingInst(false);
    }
  };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await api.post(`/projects/${id}/files`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      if (res.data.status === "failed") toast.error(`Processing failed: ${res.data.error}`);
      else toast.success(`${res.data.filename} indexed (${res.data.chunkCount} chunks)`);
      load();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const deleteFile = async (fid) => {
    try {
      await api.delete(`/files/${fid}`);
      toast.success("File removed");
      load();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const addMemory = async () => {
    if (!memInput.trim()) return;
    try {
      await api.post("/memory", { content: memInput.trim(), projectId: id });
      setMemInput("");
      toast.success("Saved to project memory");
      load();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const deleteMemory = async (mid) => {
    try {
      await api.delete(`/memory/${mid}`);
      load();
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  const deleteProject = async () => {
    try {
      await api.delete(`/projects/${id}`);
      toast.success("Project deleted");
      navigate("/projects");
    } catch (e) {
      toast.error(formatApiError(e));
    }
  };

  if (!data) {
    return (
      <div className="flex h-screen w-full bg-background">
        <IconRail />
        <div className="flex flex-1 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      </div>
    );
  }

  const { project, files, conversations, memories } = data;

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-8">
          <button onClick={() => navigate("/projects")} className="mb-5 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="back-to-projects">
            <ArrowLeft className="h-4 w-4" /> All projects
          </button>

          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="truncate text-2xl font-bold tracking-tight sm:text-3xl">{project.name}</h1>
              {project.description && <p className="mt-1.5 text-sm text-muted-foreground">{project.description}</p>}
            </div>
            <div className="flex shrink-0 gap-2">
              <Button onClick={() => navigate(`/?project=${id}`)} data-testid="project-new-chat" className="gap-2 font-semibold">
                <MessageSquare className="h-4 w-4" /> New chat
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" size="icon" data-testid="delete-project-button" className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete project?</AlertDialogTitle>
                    <AlertDialogDescription>This deletes the project, its files and memory. Conversations are detached, not deleted.</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={deleteProject} data-testid="confirm-delete-project" className="bg-destructive text-destructive-foreground hover:bg-destructive/90">Delete</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>

          {/* Files */}
          <Section title="Knowledge files" hint="PDF, DOCX, XLSX, CSV, TXT, MD, JSON — extracted, embedded and searchable.">
            <input ref={fileRef} type="file" onChange={onUpload} className="hidden" data-testid="file-input"
              accept=".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.markdown,.json,.log" />
            <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="upload-file-button" className="gap-2 border-border bg-card">
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload document
            </Button>
            <div className="mt-4 space-y-2">
              {files.length === 0 && <p className="text-sm text-muted-foreground">No files yet.</p>}
              {files.map((f) => {
                const s = STATUS[f.status] || STATUS.processing;
                return (
                  <div key={f.id} data-testid={`file-item-${f.id}`} className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{f.filename}</p>
                      <p className="text-[11px] text-muted-foreground">{(f.size / 1024).toFixed(1)} KB · {f.chunkCount} chunks</p>
                    </div>
                    <span className={`flex items-center gap-1 text-[11px] font-medium ${s.cls}`}><s.icon className="h-3.5 w-3.5" /> {s.label}</span>
                    <button onClick={() => deleteFile(f.id)} data-testid={`delete-file-${f.id}`} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                );
              })}
            </div>
          </Section>

          {/* Instructions */}
          <Section title="Custom instructions" hint="Applied to every conversation inside this project.">
            <Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} data-testid="project-instructions-textarea"
              placeholder="e.g. Always answer as a senior analyst. Prefer bullet points." className="min-h-[90px] bg-card" />
            <Button onClick={saveInstructions} disabled={savingInst} data-testid="save-instructions-button" variant="outline" className="mt-3 gap-2 border-border bg-card">
              {savingInst ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save
            </Button>
          </Section>

          {/* Memory */}
          <Section title="Project memory" hint="Facts RADHA should remember for this project. You are always in control.">
            <div className="flex gap-2">
              <Input value={memInput} onChange={(e) => setMemInput(e.target.value)} data-testid="memory-input"
                onKeyDown={(e) => e.key === "Enter" && addMemory()} placeholder="e.g. Our fiscal year starts in April." className="bg-card" />
              <Button onClick={addMemory} data-testid="add-memory-button" variant="outline" className="gap-2 border-border bg-card"><Plus className="h-4 w-4" /> Add</Button>
            </div>
            <div className="mt-3 space-y-2">
              {memories.length === 0 && <p className="text-sm text-muted-foreground">No memories yet.</p>}
              {memories.map((m) => (
                <div key={m.id} data-testid={`memory-item-${m.id}`} className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
                  <Brain className="h-4 w-4 shrink-0 text-primary" />
                  <p className="min-w-0 flex-1 text-sm">{m.content}</p>
                  <button onClick={() => deleteMemory(m.id)} data-testid={`delete-memory-${m.id}`} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              ))}
            </div>
          </Section>

          {/* Conversations */}
          <Section title="Conversations" hint="Chats grounded in this project's files and memory.">
            <div className="space-y-2">
              {conversations.length === 0 && <p className="text-sm text-muted-foreground">No conversations yet. Start a new chat.</p>}
              {conversations.map((c) => (
                <button key={c.id} data-testid={`project-conversation-${c.id}`} onClick={() => navigate(`/?conversation=${c.id}`)}
                  className="flex w-full items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5 text-left transition-colors hover:border-primary/50 hover:bg-[#171B26]">
                  <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="truncate text-sm">{c.title}</span>
                </button>
              ))}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <div className="mt-8 border-t border-border pt-6">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {hint && <p className="mb-4 mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      {children}
    </div>
  );
}

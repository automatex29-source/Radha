import { useEffect, useState } from "react";
import PageHero from "@/components/PageHero";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import IconRail from "@/components/IconRail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { FolderKanban, Plus, FileText, MessageSquare, Loader2, Sparkles } from "lucide-react";
import { ASSISTANT_TEMPLATES } from "@/lib/assistantTemplates";

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", instructions: "" });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/projects");
      setProjects(data);
    } catch (e) {
      toast.error(formatApiError(e));
      setProjects([]);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/projects", form);
      setOpen(false);
      setForm({ name: "", description: "", instructions: "" });
      toast.success("Project created");
      navigate(`/projects/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const [starting, setStarting] = useState(null);
  const startTemplate = async (t) => {
    setStarting(t.name);
    try {
      const { data } = await api.post("/projects", { name: t.name, description: t.description, instructions: t.instructions });
      navigate(`/?project=${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setStarting(null);
    }
  };

  return (
    <div className="flex h-dvh w-full overflow-hidden krish-canvas max-md:flex-col">
      <IconRail />
      <div className="radha-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
          <PageHero icon={FolderKanban} title="Projects" subtitle="Group conversations, files and knowledge. Krish AI grounds answers in a project's documents.">
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button data-testid="new-project-button" className="gap-2 font-semibold"><Plus className="h-4 w-4" /> New project</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create project</DialogTitle>
                  <DialogDescription>Group conversations and documents. Krish AI grounds answers in this project's files.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="p-name">Name</Label>
                    <Input id="p-name" data-testid="project-name-input" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Acme Research" className="bg-card" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="p-desc">Description</Label>
                    <Input id="p-desc" data-testid="project-description-input" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} placeholder="What is this project about?" className="bg-card" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="p-inst">Custom instructions (optional)</Label>
                    <Textarea id="p-inst" data-testid="project-instructions-input" value={form.instructions} onChange={(e) => setForm((f) => ({ ...f, instructions: e.target.value }))} placeholder="How should Krish AI behave inside this project?" className="min-h-[90px] bg-card" />
                  </div>
                </div>
                <DialogFooter>
                  <Button onClick={create} disabled={busy || !form.name.trim()} data-testid="create-project-submit" className="font-semibold">
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create project"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </PageHero>

          <section className="mt-8" data-testid="assistant-templates">
            <h2 className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-primary" /> Ready-made assistants</h2>
            <p className="mt-1 text-xs text-muted-foreground">Each one is a project with its own instructions. Add files to teach it more, change how it behaves, or share it with a link.</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {ASSISTANT_TEMPLATES.map((t) => (
                <button key={t.name} onClick={() => startTemplate(t)} disabled={!!starting} data-testid={`assistant-template-${t.name}`}
                  className="radha-lift flex items-start gap-3 rounded-xl border border-border bg-card p-3.5 text-left hover:border-primary/50 disabled:opacity-60">
                  <span className="text-2xl leading-none" aria-hidden>{t.emoji}</span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5 text-sm font-semibold">{t.name}{starting === t.name && <Loader2 className="h-3.5 w-3.5 animate-spin" />}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{t.description}</span>
                  </span>
                </button>
              ))}
            </div>
          </section>

          <h2 className="mt-10 text-sm font-semibold">Your projects and assistants</h2>
          <div className="mt-3">
            {projects === null ? (
              <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
            ) : projects.length === 0 ? (
              <div data-testid="projects-empty" className="rounded-2xl border border-dashed border-border py-20 text-center">
                <FolderKanban className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
                <p className="text-sm font-medium">No projects yet</p>
                <p className="mt-1 text-sm text-muted-foreground">Create a project and upload documents to ground Krish AI.</p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {projects.map((p) => (
                  <button key={p.id} data-testid={`project-card-${p.id}`} onClick={() => navigate(`/projects/${p.id}`)}
                    className="radha-lift group rounded-xl border border-border bg-card p-5 text-left hover:border-primary/50">
                    <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-surface-strong text-primary transition-colors group-hover:bg-primary group-hover:text-white">
                      <FolderKanban className="h-5 w-5" />
                    </div>
                    <p className="truncate font-semibold tracking-tight">{p.name}</p>
                    <p className="mt-1 line-clamp-2 min-h-[2.5rem] text-xs text-muted-foreground">{p.description || "No description"}</p>
                    <div className="mt-3 flex items-center gap-4 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1"><FileText className="h-3 w-3" /> {p.fileCount}</span>
                      <span className="flex items-center gap-1"><MessageSquare className="h-3 w-3" /> {p.conversationCount}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

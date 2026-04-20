import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import ShellPage from './ShellPage'

type FeaturePlaceholderPageProps = {
  title: string
  description: string
}

export default function FeaturePlaceholderPage({ title, description }: FeaturePlaceholderPageProps) {
  return (
    <ShellPage description={description} title={title}>
      <Card className="max-w-2xl border border-slate-800/90 bg-slate-900/70">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-slate-300">
          This route is wired and protected in Sprint 3. Feature implementation continues in Sprint 4/5.
        </CardContent>
      </Card>
    </ShellPage>
  )
}

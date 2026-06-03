import { ArticleDetail } from "@/components/article-detail";


export default async function ArticleDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ArticleDetail id={Number(id)} />;
}


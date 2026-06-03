from fastapi import APIRouter

from app.api.routes import article_jobs, clusters, content_rules, health, logs, products, settings, sources, standard_post_batches, workflow


router = APIRouter(prefix="/api")
router.include_router(health.router, tags=["health"])
router.include_router(settings.router, tags=["settings"])
router.include_router(content_rules.router, tags=["content-rules"])
router.include_router(article_jobs.router, prefix="/article-jobs", tags=["article-jobs"])
router.include_router(standard_post_batches.router, prefix="/standard-post-batches", tags=["standard-post-batches"])
router.include_router(products.router, prefix="/products", tags=["products"])
router.include_router(sources.router, prefix="/sources", tags=["sources"])
router.include_router(clusters.router, prefix="/content-clusters", tags=["content-clusters"])
router.include_router(logs.router, prefix="/logs", tags=["logs"])
router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])

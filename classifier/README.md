# Classifier Service

LangChain-powered AI worker for issue analysis and enrichment.

## Purpose

This service consumes raw GitHub issues from Kafka, uses LangChain with OpenAI to classify and enrich them with metadata, and stores the results in PostgreSQL with vector embeddings.

## Features

- LangChain integration for AI processing
- OpenAI API for issue classification
- Vector embedding generation with pgvector
- Kafka consumer for raw issues
- PostgreSQL storage for enriched data

## Setup

Coming soon - see main project README for development setup.

## AI Classification

- Issue type detection (bug, feature, question, etc.)
- Priority assessment
- Component/module identification
- Sentiment analysis
- Similar issue detection via vector search

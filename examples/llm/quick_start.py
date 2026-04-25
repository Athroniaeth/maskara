import asyncio

from piighost import Anonymizer, ExactMatchDetector
from piighost.pipeline import AnonymizationPipeline

detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
pipeline = AnonymizationPipeline(detector=detector, anonymizer=Anonymizer())


async def main():
    anonymized, _ = await pipeline.anonymize("Patrick habite à Paris.")
    print(anonymized)
    # <<PERSON:1>> habite à <<LOCATION:1>>.


asyncio.run(main())

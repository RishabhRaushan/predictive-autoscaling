apiVersion: batch/v1
kind: Job
metadata:
  name: k6-replay
  namespace: autoscale-lab
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: k6
          image: grafana/k6:0.52.0
          imagePullPolicy: IfNotPresent
          args: ["run", "/scripts/replay.js"]
          env:
            - name: TARGET
              value: http://demo-app.autoscale-lab.svc
            - name: PROFILE
              value: /scripts/profile.json
            - name: BUCKET_SECONDS
              value: "__BUCKET_SECONDS__"
            - name: START_EPOCH_MS
              value: "__START_EPOCH_MS__"
          volumeMounts:
            - name: scripts
              mountPath: /scripts
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
      volumes:
        - name: scripts
          configMap:
            name: k6-replay

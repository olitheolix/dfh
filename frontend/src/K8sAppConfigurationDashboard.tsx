import { useParams } from 'react-router-dom';
import { Grid, Paper } from '@mui/material';

import K8sAppConfigurationDialog from './K8sAppConfigurationDialog';
import K8sPodList from './K8sPodList';


export default function K8sAppConfigurationDashboard() {
    const { appId, envId } = useParams();

    return (
        <Grid container spacing={3}>
            {/* Configure App */}
            <Grid item xs={12}>
                <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', }}>
                    <K8sAppConfigurationDialog />
                </Paper>
            </Grid>

            {/* Show Pods */}
            <Grid item xs={12}>
                <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column' }}>
                    <K8sPodList appId={appId as string} envId={envId as string} />
                </Paper>
            </Grid>
        </Grid>

    )
}
